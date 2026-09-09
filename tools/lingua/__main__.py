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
import sys
from pathlib import Path

from . import corpora as corporamod
from . import dimensions
from .corpora import CorpusError
from .dimensions.base import LinguaDataError, SetContext, read_payload
from .extract import build_extract
from .manifest import write_manifest_and_clean
from .model import Chapter, ScanError
from .render import render_all
from .status import (
    MOUNT_HINT, RegisterBundle, all_ok, build_bundle, print_status,
    state_summary,
)

ROOT = Path(__file__).resolve().parents[2]


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
    chapters = [c for b in bundles for c in b.corpus.chapters]
    by_id = {c.id: c for c in chapters}

    def resolve(chapter_id: str) -> Chapter:
        """Full ids ("fewshot-works-academy/v1/foundations/02"), or the shorthands
        "<corpus>/<group>/<NN>" / "<group>/<NN>" when exactly one mounted
        register matches (a segment count matches only its own form)."""
        if chapter_id in by_id:
            return by_id[chapter_id]
        matches = [
            c for c in chapters
            if c.local_id == chapter_id
            or f"{c.corpus}/{c.group}/{c.number}" == chapter_id
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise CorpusError(
                f"ambiguous chapter id {chapter_id!r} — candidates: "
                + ", ".join(c.id for c in matches)
            )
        raise CorpusError(f"no such chapter: {chapter_id}")

    return resolve


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
