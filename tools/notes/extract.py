"""Build the chapter source bundle consumed by authoring/validation subagents.

The bundle is plain text on stdout: chapter metadata, the register's
translation requirements, the doc body, lab README and sources, and the
currently curated schematic + key facts. Verbatim file contents are wrapped in
sentinel lines (<<<BEGIN x>>> / <<<END x>>>) rather than ``` fences, because
chapter docs contain fenced blocks of their own.
"""

import yaml

from .gittree import lab_files
from .model import Chapter, Corpus
from .sources.base import parse_frontmatter
from .translation import mode_status

DOC_CAP = 40_000
README_CAP = 15_000
PY_CAP = 12_000
MAX_PY_FILES = 8


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... truncated {len(text) - limit} chars ...]"


def _block(tag: str, content: str) -> str:
    return f"<<<BEGIN {tag}>>>\n{content.rstrip()}\n<<<END {tag}>>>\n"


def _yaml_or_none(entry: dict | None) -> str:
    if not entry:
        return "none"
    return yaml.safe_dump(entry, sort_keys=False, allow_unicode=True, width=4096)


def build_extract(chapter: Chapter, corpus: Corpus) -> str:
    root = corpus.root
    lab_rel = (
        chapter.lab_path.relative_to(root).as_posix()
        if chapter.lab_path else "none (concept chapter)"
    )
    out = [
        f"# Extract: {chapter.id} — {chapter.title}",
        "",
        f"- id: {chapter.id}",
        f"- content_hash: {chapter.content_hash}",
        f"- group: {chapter.group}   chapter: {chapter.number}   slug: {chapter.slug}",
        f"- doc: {chapter.doc_path.relative_to(root).as_posix()}",
        f"- doc_url: {chapter.doc_url or 'none'}",
        f"- lab: {lab_rel}",
        f"- schematic_state: {chapter.schematic_state}   facts_state: {chapter.facts_state}",
        f"- components (curated): {', '.join(chapter.components) or 'none'}",
        f"- components (detected): {', '.join(chapter.detected_components) or 'none'}",
    ]
    if chapter.lab_deps:
        out.append(f"- lab_deps: {', '.join(chapter.lab_deps)}")
    if chapter.time_cost:
        out.append(f"- {chapter.time_cost}")
    out.append("")

    out.append(f"## Translation requirements (register {corpus.register})")
    modes = ", ".join(
        m + (" (active)" if mode_status(m) == "implemented"
             else " (recorded — not yet rendered)")
        for m in corpus.modes
    )
    out.append(f"- modes: {modes or 'none'}")
    if corpus.label:
        out.append(f"- label: {corpus.label}")
    out.append("")
    if corpus.translation_notes:
        out.append(_block("translation-notes", corpus.translation_notes))

    _, doc_body = parse_frontmatter(chapter.doc_path.read_text())
    out.append("## Chapter document")
    out.append(_block("doc", _cap(doc_body, DOC_CAP)))

    if chapter.lab_path is not None:
        readme = chapter.lab_path / "README.md"
        if readme.exists():
            out.append("## Lab README")
            out.append(_block("lab-readme", _cap(readme.read_text(errors="replace"), README_CAP)))
        files = [p for p in lab_files(chapter.lab_path) if p.name != "README.md"]
        py_files = [p for p in files if p.suffix == ".py"]
        for p in py_files[:MAX_PY_FILES]:
            rel = p.relative_to(chapter.lab_path).as_posix()
            out.append(f"## Lab source: {rel}")
            out.append(_block(f"py:{rel}", _cap(p.read_text(errors="replace"), PY_CAP)))
        other = [p for p in files if p.suffix != ".py"] + py_files[MAX_PY_FILES:]
        if other:
            out.append("## Other lab files (names only)")
            out.extend(f"- {p.relative_to(chapter.lab_path).as_posix()}" for p in other)
            out.append("")

    out.append(
        f"## Current curated schematic "
        f"(corpora/{chapter.corpus}/{chapter.register}/data/flows.yaml entry)")
    out.append(_block("flow-yaml", _yaml_or_none(chapter.flow)))
    out.append(
        f"## Current curated key facts "
        f"(corpora/{chapter.corpus}/{chapter.register}/data/facts.yaml entry)")
    out.append(_block("facts-yaml", _yaml_or_none(chapter.facts)))
    return "\n".join(out)
