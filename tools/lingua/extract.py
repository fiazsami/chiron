"""Build the chapter source bundle consumed by authoring/validation subagents.

The bundle is plain text on stdout: chapter metadata, the register's
translation requirements, the methodology for each active dimension (embedded
so the modular plans in methodology/ steer the agents directly), the
chapter's content, and the currently stored entries anchored in it. Verbatim
content is wrapped in sentinel lines (<<<BEGIN x>>> / <<<END x>>>) rather
than ``` fences, because chapter sources contain fenced blocks of their own.
"""

import re
from pathlib import Path

import yaml

from . import dimensions
from .model import Chapter, Corpus
from .status import RegisterBundle
from .translation import mode_status

ROOT = Path(__file__).resolve().parents[2]

DOC_CAP = 40_000
FILE_CAP = 12_000
MAX_FILES = 10
TOTAL_CAP = 80_000
METHODOLOGY_CAP = 12_000

# The methodology sections embedded into bundles — the agent-facing half of
# each modular plan (section 1 "Theory" and 5 "Worked example" stay human).
EMBEDDED_SECTIONS = ("Extraction procedure", "Schema and caps", "Quality bar")

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... truncated {len(text) - limit} chars ...]"

def _block(tag: str, content: str) -> str:
    return f"<<<BEGIN {tag}>>>\n{content.rstrip()}\n<<<END {tag}>>>\n"


def _yaml_or_none(entry) -> str:
    if not entry:
        return "none"
    return yaml.safe_dump(entry, sort_keys=False, allow_unicode=True, width=4096)


def methodology_excerpt(slug: str) -> str:
    """Sections 2-4 of methodology/<slug>.md, or a pointer when missing."""
    module = dimensions.REGISTRY[slug]
    path = ROOT / module.METHODOLOGY
    try:
        text = path.read_text()
    except OSError:
        return f"({module.METHODOLOGY} not found — extraction runs without it)"
    keep: list[str] = []
    keeping = False
    for line in text.splitlines():
        if line.startswith("## "):
            keeping = line[3:].strip() in EMBEDDED_SECTIONS
        if keeping:
            keep.append(line)
    excerpt = "\n".join(keep).strip()
    return _cap(excerpt, METHODOLOGY_CAP) if excerpt else \
        f"({module.METHODOLOGY} has no embeddable sections)"


def _doc_body(chapter: Chapter) -> str:
    raw = chapter.unit_paths[0].read_text(errors="replace")
    return _FRONTMATTER_RE.sub("", raw, count=1)


def _code_files(chapter: Chapter) -> tuple[list[Path], list[Path]]:
    """(extracted, named-only): primary first, README next, rest by size
    descending, bounded by MAX_FILES and TOTAL_CAP."""
    ordered: list[Path] = []
    if chapter.primary_path is not None:
        ordered.append(chapter.primary_path)
    readmes = [p for p in chapter.unit_paths if p.name.lower() == "readme.md"]
    for p in readmes:
        if p not in ordered:
            ordered.append(p)
    rest = [p for p in chapter.unit_paths if p not in ordered]
    ordered += sorted(rest, key=lambda p: p.stat().st_size, reverse=True)

    extracted: list[Path] = []
    budget = TOTAL_CAP
    for p in ordered:
        if len(extracted) >= MAX_FILES or budget <= 0:
            break
        extracted.append(p)
        budget -= min(p.stat().st_size, FILE_CAP)
    named_only = [p for p in chapter.unit_paths if p not in extracted]
    return extracted, named_only


def build_extract(
    chapter: Chapter,
    corpus: Corpus,
    bundle: RegisterBundle,
    mode: str | None = None,
) -> str:
    root = corpus.root
    states = bundle.chapter_states(chapter)
    modes = [mode] if mode else [m for m in bundle.tracked_modes]
    out = [
        f"# Extract: {chapter.id} — {chapter.title}",
        "",
        f"- id: {chapter.id}",
        f"- content_hash: {chapter.content_hash}",
        f"- group: {chapter.group}   chapter: {chapter.number}   slug: {chapter.slug}",
        f"- kind: {chapter.kind}",
        "- states: " + "   ".join(f"{s}={v}" for s, v in states.items()),
        "",
    ]

    out.append(f"## Translation requirements (register {corpus.register})")
    mode_line = ", ".join(
        m + (" (active)" if mode_status(m) == "implemented"
             else " (recorded — not yet implemented)")
        for m in corpus.modes
    )
    out.append(f"- modes: {mode_line or 'none'}")
    if corpus.label:
        out.append(f"- label: {corpus.label}")
    out.append("")
    if corpus.translation_notes:
        out.append(_block("translation-notes", corpus.translation_notes))

    for slug in modes:
        out.append(f"## Methodology: {slug}")
        out.append(_block(f"methodology:{slug}", methodology_excerpt(slug)))

    if chapter.kind == "doc":
        out.append("## Chapter content")
        out.append(_block("doc", _cap(_doc_body(chapter), DOC_CAP)))
    else:
        extracted, named_only = _code_files(chapter)
        for p in extracted:
            rel = p.relative_to(root).as_posix()
            out.append(f"## Chapter file: {rel}")
            out.append(_block(f"file:{rel}", _cap(p.read_text(errors="replace"), FILE_CAP)))
        if named_only:
            out.append("## Other chapter files (names only)")
            out.extend(f"- {p.relative_to(root).as_posix()}" for p in named_only)
            out.append("")

    for slug in modes:
        module = dimensions.REGISTRY[slug]
        entries = module.entries_for_chapter(bundle.data[slug], chapter.local_id)
        out.append(
            f"## Current {module.LABEL.lower()} entries anchored here "
            f"(corpora/{chapter.corpus}/{chapter.register}/data/{module.DATA_FILENAME})"
        )
        out.append(_block(f"{slug}-yaml", _yaml_or_none(entries)))

    lexmod = dimensions.REGISTRY["lexicon"]
    out.append("## Lexicon slug index")
    index = lexmod.slug_index(bundle.data.get("lexicon", {}))
    out.append(_block(
        "slug-index",
        "\n".join(index) if index else "(lexicon is empty — every slug is new)",
    ))
    return "\n".join(out)
