"""Linguistic structure extraction for the mounted corpora.

    uv run python -m tools.lingua                        # build: pages + manifest
    uv run python -m tools.lingua build --only mcp/02    # subset render while iterating
    uv run python -m tools.lingua check                  # drift report, writes nothing
    uv run python -m tools.lingua check --strict         # exit 1 unless everything ok
    uv run python -m tools.lingua status [--json]        # per-chapter, per-dimension states
    uv run python -m tools.lingua extract mcp/02         # source bundle for authoring agents
    uv run python -m tools.lingua extract mcp/02 --mode lexicon
    uv run python -m tools.lingua set lexicon mcp/02 --from payload.json [--redefine]
    uv run python -m tools.lingua accept-drift mcp/02 [--mode lexicon]   (or: all)

Chapter ids are "<corpus>/<vN>/<group>/<NN>" (fewshot-works-academy/v1/foundations/02).
Two shorthands resolve when unambiguous: "<corpus>/<group>/<NN>" (corpus has
one register) and the bare "<group>/<NN>" (one mounted register matches).
Corpora are mounted via the /mount Claude Code skill; re-running it on a
mounted corpus creates the next register (v2, v3, ...).
"""

import argparse
import os
import sys
from pathlib import Path

from . import author as authormod
from . import corpora as corporamod
from . import dimensions
from .author import AuthorError
from .corpora import CorpusError
from .dimensions.base import LinguaDataError, SetContext, read_payload
from .extract import build_extract
from .manifest import write_manifest_and_clean
from .model import Chapter, ScanError
from .render import render_all
from .status import (
    MOUNT_HINT, RegisterBundle, all_ok, build_bundle, print_status,
    resolve_factory, state_summary,
)

ROOT = Path(__file__).resolve().parents[2]


def load_env(path: Path) -> None:
    """Load KEY=value pairs from a .env file into os.environ. Real
    environment variables always win; empty values are skipped so a blank
    template line never shadows `ant auth` credential resolution."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools.lingua",
        description="Extract the linguistic structure of mounted corpora "
                    "(lexicon, phrasebook, concept relations) and render pages.",
    )
    sub = parser.add_subparsers(dest="cmd")

    build = sub.add_parser("build", help="render pages and write the manifest (the default)")
    build.add_argument("--only", action="append", metavar="ID",
                       help="render only this chapter id (repeatable); "
                            "indexes are still rebuilt")

    check = sub.add_parser("check", help="scan and report drift without writing anything")
    check.add_argument("--strict", action="store_true",
                       help="exit 1 unless every tracked state is ok and there "
                            "are no warnings")

    status = sub.add_parser("status", help="per-chapter, per-dimension extraction states")
    status.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")

    extract = sub.add_parser("extract",
                             help="print a chapter's source bundle for authoring agents")
    extract.add_argument("id", metavar="ID")
    extract.add_argument("--mode", metavar="SLUG",
                         help="trim the bundle to one dimension")

    setcmd = sub.add_parser("set",
                            help="validate a dimension payload and store it for a chapter")
    setcmd.add_argument("dimension", choices=list(dimensions.REGISTRY))
    setcmd.add_argument("id", metavar="ID")
    setcmd.add_argument("--from", dest="from_file", metavar="FILE", required=True,
                        help="JSON payload file")
    setcmd.add_argument("--redefine", action="store_true",
                        help="allow redefining a term owned by another chapter")

    author = sub.add_parser(
        "author",
        help="API-native authoring: submit, collect, and apply extraction "
             "runs (Batch API + structured outputs)")
    author.add_argument("targets", nargs="*", metavar="TARGET",
                        help="a register (<corpus>/<vN>), group, or chapter "
                             "ids — one register per run")
    author.add_argument("--mode", metavar="SLUG",
                        help="author a single dimension instead of every "
                             "not-ok tracked one")
    author.add_argument("--model", default=None,
                        help="model id (default: $CHIRON_AUTHOR_MODEL or "
                             "claude-sonnet-5)")
    author.add_argument("--effort", default=None,
                        help="low|medium|high|xhigh|max (default: "
                             "$CHIRON_AUTHOR_EFFORT or medium)")
    author.add_argument("--sync", action="store_true",
                        help="call the API synchronously instead of the "
                             "Batch API (for a handful of chapters)")
    author.add_argument("--collect", action="store_true",
                        help="fetch a submitted batch's results")
    author.add_argument("--wait", action="store_true",
                        help="with --collect: poll until the batch ends")
    author.add_argument("--apply", dest="apply_results", action="store_true",
                        help="validate and apply collected results "
                             "(single-writer; redefinitions are held for "
                             "human review)")
    author.add_argument("--check", action="store_true",
                        help="with --apply: dry-run, write nothing")
    author.add_argument("--retry", nargs="+", metavar="ID", default=None,
                        help="re-author rejected chapters with their stored "
                             "violations (synchronous)")

    drift = sub.add_parser("accept-drift",
                           help="re-pin current content hashes for stale anchors "
                                "(re-blesses content as-is; prefer re-authoring)")
    drift.add_argument("ids", nargs="+", metavar="ID",
                       help="chapter ids, or 'all' for every stale anchor everywhere")
    drift.add_argument("--mode", metavar="SLUG",
                       help="limit to one dimension")

    parser.set_defaults(cmd="build", only=None)
    return parser


def _resolve_factory(bundles: list[RegisterBundle]):
    resolve = resolve_factory(bundles)

    def wrapped(chapter_id: str) -> Chapter:
        try:
            return resolve(chapter_id)
        except ValueError as exc:
            raise CorpusError(str(exc)) from exc

    return wrapped


def _require_tracked(bundle: RegisterBundle, mode: str) -> None:
    if mode not in dimensions.REGISTRY:
        raise CorpusError(
            f"unknown dimension {mode!r} — shipped dimensions: "
            + ", ".join(dimensions.REGISTRY)
        )
    if mode not in bundle.tracked_modes:
        raise CorpusError(
            f"register {bundle.corpus.name}/{bundle.corpus.register} does not "
            f"enable mode {mode!r} — add it to translation.yaml modes first"
        )


def _set(bundle: RegisterBundle, chapter: Chapter, dimension: str,
         from_file: str, redefine: bool) -> int:
    module = dimensions.REGISTRY[dimension]
    payload = read_payload(Path(from_file))
    ctx = SetContext(chapter=chapter, corpus=bundle.corpus,
                     data=bundle.data, redefine=redefine)
    problems = module.validate_payload(payload, ctx)
    if problems:
        print(f"invalid {dimension} payload for {chapter.id}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    new_data = module.apply(bundle.data[dimension], ctx, payload)
    module.dump(bundle.data_dir / module.DATA_FILENAME, new_data)
    bundle.data[dimension] = new_data
    print(f"{chapter.id} {dimension}: ok "
          f"(anchors curated_against {chapter.content_hash})")
    return 0


def _accept_drift(bundles: list[RegisterBundle], resolve, ids: list[str],
                  mode: str | None) -> int:
    slugs = [mode] if mode else list(dimensions.REGISTRY)
    per_bundle: dict[int, list[Chapter]] = {}
    if ids == ["all"]:
        for i, bundle in enumerate(bundles):
            per_bundle[i] = list(bundle.corpus.chapters)
    else:
        keyed = {(b.corpus.name, b.corpus.register): i for i, b in enumerate(bundles)}
        for chapter_id in ids:
            chapter = resolve(chapter_id)
            per_bundle.setdefault(
                keyed[(chapter.corpus, chapter.register)], []
            ).append(chapter)
    updated: dict[str, list[str]] = {slug: [] for slug in slugs}
    for i, chapters in per_bundle.items():
        bundle = bundles[i]
        if mode:
            _require_tracked(bundle, mode)
        for slug in slugs:
            if slug not in bundle.tracked_modes:
                continue
            module = dimensions.REGISTRY[slug]
            changed = False
            for chapter in chapters:
                if module.accept_drift(bundle.data[slug], chapter):
                    changed = True
                    updated[slug].append(chapter.id)
            if changed:
                module.dump(bundle.data_dir / module.DATA_FILENAME,
                            bundle.data[slug])
    print("accepted drift: " + " | ".join(
        f"{slug} [{', '.join(chapter_ids) or '-'}]"
        for slug, chapter_ids in updated.items()
    ))
    return 0


def _pending(bundle: RegisterBundle) -> list[Chapter]:
    return [
        c for c in bundle.corpus.chapters
        if any(s != "ok" for s in bundle.chapter_states(c).values())
    ]


def _author_targets(bundles, resolve, targets):
    """Resolve author targets to (register key, chapters). Register and group
    targets take their not-ok chapters; explicit ids are taken as given.
    One register per authoring run."""
    chapters: list[Chapter] = []
    for target in targets:
        regs = [
            b for b in bundles
            if f"{b.corpus.name}/{b.corpus.register}" == target
            or b.corpus.name == target
        ]
        if len(regs) > 1:
            raise CorpusError(
                f"{target!r} matches several registers — use <corpus>/<vN>")
        if regs:
            chapters += _pending(regs[0])
            continue
        groups = [
            (b, g) for b in bundles for g in b.corpus.group_ids
            if g == target
            or f"{b.corpus.name}/{b.corpus.register}/{g}" == target
        ]
        if len(groups) > 1:
            raise CorpusError(
                f"ambiguous group {target!r} — qualify as <corpus>/<vN>/<group>")
        if groups:
            bundle, group_id = groups[0]
            chapters += [c for c in _pending(bundle) if c.group == group_id]
            continue
        chapters.append(resolve(target))
    seen: set[str] = set()
    unique = [c for c in chapters if not (c.id in seen or seen.add(c.id))]
    if not unique:
        raise CorpusError("no chapters to author (every tracked state is ok?)")
    keys = {(c.corpus, c.register) for c in unique}
    if len(keys) > 1:
        raise CorpusError(
            "one register per authoring run — targets span "
            + ", ".join(f"{n}/{r}" for n, r in sorted(keys)))
    return keys.pop(), unique


def _work_bundle(bundles: list[RegisterBundle], targets: list[str]) -> RegisterBundle:
    """The register whose authoring run --collect/--apply operate on."""
    if targets:
        regs = [
            b for b in bundles
            if f"{b.corpus.name}/{b.corpus.register}" == targets[0]
            or b.corpus.name == targets[0]
        ]
        if len(regs) == 1:
            return regs[0]
        raise CorpusError(f"{targets[0]!r} does not name exactly one register")
    with_runs = [
        b for b in bundles if (authormod.work_dir(b) / "run.json").exists()
    ]
    if len(with_runs) == 1:
        return with_runs[0]
    raise CorpusError(
        "name the register, e.g.: author --collect <corpus>/<vN>")


def _report(bundles: list[RegisterBundle], warnings: list[str]) -> None:
    chapters = [(b, c) for b in bundles for c in b.corpus.chapters]
    combined: dict[str, dict] = {}
    for bundle in bundles:
        for slug, counter in bundle.state_counters().items():
            combined.setdefault(slug, type(counter)()).update(counter)
    parts = [
        f"{slug} {state_summary(counter) or '-'}"
        for slug, counter in combined.items()
    ]
    print(f"{len(chapters)} chapters | " + (" | ".join(parts) or "no tracked modes"))
    # Detail lines for actionable drift; bare "none" states are summarized in
    # one line per dimension so unauthored chapters don't flood build output.
    none_counts: dict[str, int] = {}
    for bundle, chapter in chapters:
        states = bundle.chapter_states(chapter)
        if any(state == "stale" for state in states.values()):
            line = "   ".join(f"{slug} {state}" for slug, state in states.items())
            print(f"  {chapter.id:<40} {line}  (content {chapter.content_hash})")
        for slug, state in states.items():
            if state == "none":
                none_counts[slug] = none_counts.get(slug, 0) + 1
    for slug, count in none_counts.items():
        print(f"  {count} chapter(s) have no {slug} entries yet (author via /translate)")
    for warning in warnings:
        print(f"  warning: {warning}")


def main(argv: list[str] | None = None, corpora_dir: Path | None = None) -> int:
    corpora_dir = corpora_dir or ROOT / "corpora"
    load_env(ROOT / ".env")
    args = _parser().parse_args(argv)

    try:
        configs, warnings = corporamod.discover(corpora_dir)
        bundles = []
        for cfg in configs:
            corpus = corporamod.scan_corpus(cfg)
            bundle = build_bundle(corpus, cfg.data_dir)
            warnings += corpus.warnings + bundle.warnings
            bundles.append(bundle)
    except (CorpusError, ScanError, LinguaDataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not bundles:
        if args.cmd == "status":
            return print_status(bundles, args.json)
        print(MOUNT_HINT)
        return 1 if args.cmd == "check" and args.strict else 0

    resolve = _resolve_factory(bundles)
    by_key = {(b.corpus.name, b.corpus.register): b for b in bundles}

    try:
        if args.cmd == "status":
            return print_status(bundles, args.json)

        if args.cmd == "extract":
            chapter = resolve(args.id)
            bundle = by_key[(chapter.corpus, chapter.register)]
            if args.mode:
                _require_tracked(bundle, args.mode)
            print(build_extract(chapter, bundle.corpus, bundle, args.mode))
            return 0

        if args.cmd == "set":
            chapter = resolve(args.id)
            bundle = by_key[(chapter.corpus, chapter.register)]
            _require_tracked(bundle, args.dimension)
            return _set(bundle, chapter, args.dimension, args.from_file,
                        args.redefine)

        if args.cmd == "accept-drift":
            return _accept_drift(bundles, resolve, args.ids, args.mode)

        if args.cmd == "author":
            model = (args.model or os.environ.get("CHIRON_AUTHOR_MODEL")
                     or authormod.DEFAULT_MODEL)
            effort = (args.effort or os.environ.get("CHIRON_AUTHOR_EFFORT")
                      or authormod.DEFAULT_EFFORT)
            try:
                import anthropic as _anthropic_mod
                api_errors: tuple = (_anthropic_mod.APIError,)
            except ImportError:
                api_errors = ()
            try:
                if args.retry:
                    chapters = [resolve(i) for i in args.retry]
                    bundle = by_key[(chapters[0].corpus, chapters[0].register)]
                    return authormod.retry(bundle, chapters, model, effort)
                if args.collect:
                    return authormod.collect(
                        _work_bundle(bundles, args.targets), args.wait)
                if args.apply_results:
                    return authormod.apply_results(
                        _work_bundle(bundles, args.targets), args.check)
                if not args.targets:
                    raise CorpusError(
                        "author needs a target: a register (<corpus>/<vN>), "
                        "a group, or chapter ids")
                key, chapters = _author_targets(bundles, resolve, args.targets)
                bundle = by_key[key]
                if args.mode:
                    _require_tracked(bundle, args.mode)
                return authormod.submit(bundle, chapters, args.mode, model,
                                        effort, args.sync)
            except (AuthorError, *api_errors) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            except TypeError as exc:
                # The SDK raises a bare TypeError when no credential source
                # resolves; anything else is a real bug — re-raise it.
                if "authentication" not in str(exc).lower():
                    raise
                print(f"error: {authormod._auth_error(exc)}", file=sys.stderr)
                return 2
    except (CorpusError, LinguaDataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "build":
        try:
            only = {resolve(i).id for i in args.only} if args.only else None
        except CorpusError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        written = render_all(bundles, corpora_dir, only=only)
        removed = write_manifest_and_clean(corpora_dir, bundles)
        print(f"wrote {len(written)} pages under "
              f"corpora/<corpus>/<vN>/pages/"
              + (f", removed {len(removed)} stale" if removed else ""))

    _report(bundles, warnings)

    if args.cmd == "check" and args.strict and (not all_ok(bundles) or warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
