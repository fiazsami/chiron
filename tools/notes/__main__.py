"""Turnkey notes generator for the mounted corpora.

    uv run python -m tools.notes                       # full rebuild
    uv run python -m tools.notes --check               # drift report, writes nothing
    uv run python -m tools.notes --strict              # exit 1 unless everything is curated ok
    uv run python -m tools.notes --accept-drift foundations/06   (or: all)
    uv run python -m tools.notes --only mcp/02         # subset render while iterating
    uv run python -m tools.notes --status [--json]     # per-chapter content-type report
    uv run python -m tools.notes --extract mcp/02      # source bundle for authoring agents
    uv run python -m tools.notes --set-facts mcp/02 --from payload.json

Chapter ids are "<corpus>/<vN>/<group>/<NN>" (fewshot-works-academy/v1/foundations/02). Two
shorthands resolve when unambiguous: "<corpus>/<group>/<NN>" (corpus has one
register) and the bare "<group>/<NN>" (one mounted register matches).
Corpora are mounted via the /mount Claude Code skill; re-running it on a
mounted corpus creates the next register (v2, v3, ...).
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import corpora as corporamod
from . import facts as factsmod
from . import flows as flowsmod
from .corpora import CorpusError
from .extract import build_extract
from .facts import FactsDataError, apply_facts, load_facts, validate_payload
from .flows import FlowDataError, apply_flows, load_flows
from .manifest import write_manifest_and_clean
from .model import Chapter, Corpus, ScanError
from .render import FACTS_STATES, SCHEMATIC_STATES, render_all, state_summary

ROOT = Path(__file__).resolve().parents[2]
CORPORA_DIR = ROOT / "corpora"

MOUNT_HINT = (
    "no corpora mounted under corpora/ — run /mount <repo-url> in Claude Code "
    "to mount one"
)


def _flows_path(corpus: Corpus) -> Path:
    return CORPORA_DIR / corpus.name / corpus.register / "data" / "flows.yaml"


def _facts_path(corpus: Corpus) -> Path:
    return CORPORA_DIR / corpus.name / corpus.register / "data" / "facts.yaml"


def _print_status(corpora: list[Corpus], as_json: bool) -> int:
    chapters = [c for corpus in corpora for c in corpus.chapters]
    sch = Counter(c.schematic_state for c in chapters)
    fac = Counter(c.facts_state for c in chapters)
    if as_json:
        print(json.dumps({
            "corpora": [
                {
                    "name": s.name, "register": s.register, "label": s.label,
                    "checkout": s.checkout, "modes": s.modes,
                }
                for s in corpora
            ],
            "chapters": [
                {
                    "id": c.id, "corpus": c.corpus, "register": c.register,
                    "group": c.group, "number": c.number,
                    "title": c.short_title, "concept_only": c.concept_only,
                    "content_hash": c.content_hash,
                    "schematic": c.schematic_state, "facts": c.facts_state,
                    "page": c.page_relpath,
                }
                for c in chapters
            ],
            "totals": {"schematic": dict(sch), "facts": dict(fac)},
        }, indent=2))
    else:
        if not corpora:
            print(MOUNT_HINT)
            return 0
        id_w = max(32, *(len(c.id) + 1 for c in chapters)) if chapters else 32
        print(f"{'id':<{id_w}} {'schematic':<10} facts")
        for c in chapters:
            print(f"{c.id:<{id_w}} {c.schematic_state:<10} {c.facts_state}")
        print(f"\n{len(chapters)} chapters | "
              f"schematic {state_summary(sch, SCHEMATIC_STATES)} | "
              f"facts {state_summary(fac, FACTS_STATES)}")
    return 0


def _set_facts(corpus: Corpus, chapter: Chapter, from_file: str) -> int:
    payload = factsmod.read_payload(Path(from_file))
    problems = validate_payload(payload)
    if problems:
        print(f"invalid facts payload for {chapter.id}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    factsmod.set_facts(_facts_path(corpus), chapter, payload, corpus.group_ids)
    print(f"{chapter.id} facts: ok (curated_against {chapter.content_hash})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.notes",
        description="Generate Markdown notes pages (key facts + SVG schematics) for mounted corpora.",
    )
    parser.add_argument("--check", action="store_true",
                        help="scan and report drift without writing anything")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 unless every chapter's schematic and key facts are ok")
    parser.add_argument("--accept-drift", nargs="+", metavar="ID",
                        help="re-pin current content hashes in flows.yaml and facts.yaml "
                             "for these chapter ids (or 'all' for every stale entry "
                             "across every register of every corpus)")
    parser.add_argument("--only", action="append", metavar="ID",
                        help="render only this chapter id (repeatable); index is still rebuilt")
    parser.add_argument("--status", action="store_true",
                        help="report each chapter's content types (schematic / key facts) and freshness")
    parser.add_argument("--json", action="store_true",
                        help="with --status: emit machine-readable JSON")
    parser.add_argument("--extract", metavar="ID",
                        help="print the chapter's source bundle for authoring/validation agents")
    parser.add_argument("--set-facts", dest="set_facts", metavar="ID",
                        help="validate a key-facts JSON payload and store it for this chapter")
    parser.add_argument("--from", dest="from_file", metavar="FILE",
                        help="JSON payload file for --set-facts")
    args = parser.parse_args(argv)

    if sum(map(bool, (args.check, args.status, args.extract, args.set_facts))) > 1:
        parser.error("--check, --status, --extract and --set-facts are mutually exclusive")
    if args.json and not args.status:
        parser.error("--json only applies to --status")
    if bool(args.set_facts) != bool(args.from_file):
        parser.error("--set-facts and --from FILE must be used together")

    def load_and_apply(corpus: Corpus) -> list[str]:
        flows_where = f"corpora/{corpus.name}/{corpus.register}/data/flows.yaml"
        facts_where = f"corpora/{corpus.name}/{corpus.register}/data/facts.yaml"
        return (apply_flows(corpus.chapters, load_flows(_flows_path(corpus)), flows_where)
                + apply_facts(corpus.chapters, load_facts(_facts_path(corpus)), facts_where))

    try:
        configs, warnings = corporamod.discover(CORPORA_DIR)
        corpora = [corporamod.scan_corpus(cfg) for cfg in configs]
        for corpus in corpora:
            warnings += load_and_apply(corpus)
    except (CorpusError, ScanError, FlowDataError, FactsDataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not corpora:
        if args.status:
            return _print_status(corpora, args.json)
        print(MOUNT_HINT)
        return 1 if args.strict else 0

    chapters = [c for corpus in corpora for c in corpus.chapters]
    by_id = {c.id: c for c in chapters}
    corpus_by_key = {(s.name, s.register): s for s in corpora}

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

    resolved: dict[str, Chapter] = {}
    try:
        for chapter_id in [args.extract, args.set_facts, *(args.only or []),
                           *(args.accept_drift or [])]:
            if chapter_id and chapter_id != "all":
                resolved[chapter_id] = resolve(chapter_id)
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.accept_drift:
        try:
            per_corpus: dict[tuple[str, str], list[str]] = {}
            if args.accept_drift == ["all"]:
                per_corpus = {(s.name, s.register): ["all"] for s in corpora}
            else:
                for chapter_id in args.accept_drift:
                    chapter = resolved[chapter_id]
                    per_corpus.setdefault(
                        (chapter.corpus, chapter.register), []
                    ).append(chapter.local_id)
            updated_flows: list[str] = []
            updated_facts: list[str] = []
            warnings = []
            for corpus in corpora:
                ids = per_corpus.get((corpus.name, corpus.register))
                if ids:
                    updated_flows += flowsmod.accept_drift(
                        _flows_path(corpus), corpus.chapters, ids)
                    updated_facts += factsmod.accept_drift(
                        _facts_path(corpus), corpus.chapters, ids, corpus.group_ids)
                warnings += load_and_apply(corpus)
            print(f"accepted drift: flows [{', '.join(updated_flows) or '-'}] | "
                  f"facts [{', '.join(updated_facts) or '-'}]")
        except (FlowDataError, FactsDataError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    for corpus in corpora:
        warnings += corpus.warnings

    if args.status:
        return _print_status(corpora, args.json)
    if args.extract:
        chapter = resolved[args.extract]
        print(build_extract(chapter, corpus_by_key[(chapter.corpus, chapter.register)]))
        return 0
    if args.set_facts:
        chapter = resolved[args.set_facts]
        try:
            return _set_facts(
                corpus_by_key[(chapter.corpus, chapter.register)], chapter, args.from_file)
        except FactsDataError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if not args.check:
        only = {c.id for k, c in resolved.items() if k in (args.only or [])} or None
        written = render_all(corpora, CORPORA_DIR, only=only)
        removed = write_manifest_and_clean(CORPORA_DIR, corpora)
        pages = sum(1 for p in written if p.suffix == ".md")
        print(f"wrote {pages} pages under {CORPORA_DIR.relative_to(ROOT)}/<corpus>/<vN>/notes/"
              + (f", removed {len(removed)} stale" if removed else ""))

    sch = Counter(c.schematic_state for c in chapters)
    fac = Counter(c.facts_state for c in chapters)
    labs = sum(1 for c in chapters if not c.concept_only)
    print(f"{len(chapters)} chapters | {labs} labs | "
          f"schematic {state_summary(sch, SCHEMATIC_STATES) or '-'} | "
          f"facts {state_summary(fac, FACTS_STATES) or '-'}")
    # Detail lines for actionable drift; a bare "facts none" is summarized in
    # one line instead so 40 unauthored chapters don't flood build output.
    for chapter in chapters:
        if chapter.schematic_state != "ok" or chapter.facts_state == "stale":
            print(f"  {chapter.id:<40} schematic {chapter.schematic_state:<8} "
                  f"facts {chapter.facts_state:<6} {chapter.short_title}  "
                  f"(content {chapter.content_hash})")
    if fac["none"]:
        print(f"  {fac['none']} chapter(s) have no key facts yet (author via /update-notes)")
    for warning in warnings:
        print(f"  warning: {warning}")

    all_ok = all(
        c.schematic_state == "ok" and c.facts_state == "ok" for c in chapters
    )
    if args.strict and (not all_ok or warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
