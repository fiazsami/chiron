"""Shared machinery for linguistic dimensions.

Every dimension stores corpus-scoped entries in one machine-owned YAML file
under the register's data/ dir, grounded by ANCHORS: verbatim quotes from a
chapter's source files, pinned to the content hash the chapter had when the
quote was authored. Grounding is enforced mechanically — `set` rejects any
quote it cannot find in the anchored chapter — and drift is per-anchor: a
term anchored in three chapters goes stale only where content changed.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..model import Chapter, Corpus

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HASH_RE = re.compile(r"^[0-9a-f]{12}$")

MIN_QUOTE_CHARS = 8
MAX_QUOTE_CHARS = 240
MAX_ANCHORS_PER_ENTRY = 8

_WS_RE = re.compile(r"\s+")


class LinguaDataError(Exception):
    pass


@dataclass
class SetContext:
    """Everything a dimension needs to validate and apply one chapter's
    payload: the target chapter, its corpus (for source paths), the loaded
    data of every dimension (for cross-dimension slug checks), and whether
    the operator passed --redefine."""

    chapter: Chapter
    corpus: Corpus
    data: dict[str, dict]  # dimension slug -> loaded data
    redefine: bool = False
    # File-content cache for quote grounding, keyed by path.
    _texts: dict[Path, str] = field(default_factory=dict)

    def normalized_text(self, path: Path) -> str | None:
        if path not in self._texts:
            try:
                raw = path.read_text(errors="replace")
            except OSError:
                return None
            self._texts[path] = normalize(raw)
        return self._texts[path]


def normalize(text: str) -> str:
    """Collapse all whitespace runs so quotes match across line wraps."""
    return _WS_RE.sub(" ", text).strip()


def one_line(value: str) -> bool:
    return "\n" not in value and "\r" not in value


def check_str(problems: list[str], where: str, key: str, value,
              max_chars: int, required: bool = True, single: bool = True) -> None:
    """Append every violation of a bounded string field."""
    if value is None:
        if required:
            problems.append(f"{where}: '{key}' is required")
        return
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{where}: '{key}' must be a non-empty string")
    elif single and not one_line(value):
        problems.append(f"{where}: '{key}' must be a single line")
    elif len(value) > max_chars:
        problems.append(f"{where}: '{key}' is {len(value)} chars (max {max_chars})")


def validate_anchors(anchors, where: str, ctx: SetContext) -> list[str]:
    """Validate a payload's anchors for one entry: shape, target-chapter
    binding, and mechanical quote grounding against the chapter's files."""
    problems: list[str] = []
    if not isinstance(anchors, list) or not anchors:
        return [f"{where}: 'anchors' must be a non-empty list"]
    if len(anchors) > MAX_ANCHORS_PER_ENTRY:
        problems.append(
            f"{where}: {len(anchors)} anchors (max {MAX_ANCHORS_PER_ENTRY} per entry)"
        )
    chapter = ctx.chapter
    unit_rels = {
        p.relative_to(ctx.corpus.root).as_posix(): p for p in chapter.unit_paths
    }
    for i, anchor in enumerate(anchors):
        aw = f"{where}.anchors[{i}]"
        if not isinstance(anchor, dict):
            problems.append(f"{aw}: must be an object with 'chapter' and 'quote'")
            continue
        unknown = set(anchor) - {"chapter", "path", "quote"}
        if unknown:
            problems.append(f"{aw}: unknown key(s): {', '.join(sorted(unknown))}")
        if anchor.get("chapter") != chapter.local_id:
            problems.append(
                f"{aw}: 'chapter' must be the target chapter {chapter.local_id!r} "
                f"(got {anchor.get('chapter')!r})"
            )
        path = anchor.get("path")
        if path is None and chapter.kind == "code":
            problems.append(f"{aw}: 'path' is required for code chapters")
        elif path is not None and (not isinstance(path, str) or not path.strip()):
            problems.append(f"{aw}: 'path' must be a non-empty source-relative string")
        elif path is not None and path not in unit_rels:
            problems.append(
                f"{aw}: path {path!r} is not one of the chapter's files"
            )
        quote = anchor.get("quote")
        check_str(problems, aw, "quote", quote, MAX_QUOTE_CHARS)
        if isinstance(quote, str) and one_line(quote) and quote.strip():
            if len(quote.strip()) < MIN_QUOTE_CHARS:
                problems.append(
                    f"{aw}: quote is {len(quote.strip())} chars "
                    f"(min {MIN_QUOTE_CHARS})"
                )
            else:
                targets = (
                    [unit_rels[path]] if isinstance(path, str) and path in unit_rels
                    else chapter.unit_paths
                )
                needle = normalize(quote)
                if not any(
                    (text := ctx.normalized_text(p)) is not None and needle in text
                    for p in targets
                ):
                    problems.append(
                        f"{aw}: quote not found in the chapter's files "
                        f"(quotes must be verbatim; whitespace is normalized)"
                    )
    return problems


def stamp_anchor(anchor: dict, chapter: Chapter) -> dict:
    """Canonical stored form; the writer stamps curated_against itself so
    authors never handle hashes."""
    stamped = {"chapter": chapter.local_id}
    if anchor.get("path"):
        stamped["path"] = anchor["path"]
    stamped["quote"] = anchor["quote"].strip()
    stamped["curated_against"] = chapter.content_hash
    return stamped


def validate_stored_anchor(anchor, where: str) -> list[str]:
    """Structural check for anchors read back from a data file."""
    problems: list[str] = []
    if not isinstance(anchor, dict):
        return [f"{where}: expected a mapping"]
    if not isinstance(anchor.get("chapter"), str) or not anchor["chapter"]:
        problems.append(f"{where}: 'chapter' must be a chapter id string")
    if "path" in anchor and (not isinstance(anchor["path"], str) or not anchor["path"]):
        problems.append(f"{where}: 'path' must be a non-empty string")
    if not isinstance(anchor.get("quote"), str) or not anchor["quote"].strip():
        problems.append(f"{where}: 'quote' must be a non-empty string")
    hash_ = anchor.get("curated_against")
    if not isinstance(hash_, str) or not HASH_RE.fullmatch(hash_):
        problems.append(f"{where}: 'curated_against' must be a 12-hex content hash")
    unknown = set(anchor) - {"chapter", "path", "quote", "curated_against"}
    if unknown:
        problems.append(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
    return problems


def drop_chapter_anchors(anchors: list[dict], local_id: str) -> list[dict]:
    return [a for a in anchors if a.get("chapter") != local_id]


def anchor_state(anchors: list[dict], chapter: Chapter) -> str:
    """none | stale | ok for one chapter's contribution to an anchor list."""
    mine = [a for a in anchors if a.get("chapter") == chapter.local_id]
    if not mine:
        return "none"
    if any(a.get("curated_against") != chapter.content_hash for a in mine):
        return "stale"
    return "ok"


def repin_anchors(anchors: list[dict], chapter: Chapter) -> int:
    """accept-drift: re-pin this chapter's stale anchors to its current hash.
    Re-blesses content as-is — prefer re-authoring via /translate."""
    changed = 0
    for anchor in anchors:
        if (anchor.get("chapter") == chapter.local_id
                and anchor.get("curated_against") != chapter.content_hash):
            anchor["curated_against"] = chapter.content_hash
            changed += 1
    return changed


def orphan_warnings(anchors_by_owner: dict[str, list[dict]],
                    known_chapters: set[str], where: str) -> list[str]:
    """Warn about anchors referencing chapters that no longer exist."""
    orphaned = sorted({
        a["chapter"]
        for anchors in anchors_by_owner.values()
        for a in anchors
        if a.get("chapter") not in known_chapters
    })
    return [
        f"{where}: anchors reference no current chapter {cid!r} (removed or renamed?)"
        for cid in orphaned
    ]


def header(dimension_slug: str, noun: str) -> str:
    return (
        f"# Extracted {noun} for this register — one dimension of its\n"
        f"# linguistic structure. MACHINE-OWNED: written by\n"
        f"#   uv run python -m tools.lingua set {dimension_slug} <chapter-id> --from <payload.json>\n"
        f"# Do not hand-edit; the whole file is rewritten in canonical form on\n"
        f"# every write, and comments other than this header are not preserved.\n\n"
    )


def dump_yaml(path: Path, data, dimension_slug: str, noun: str) -> None:
    body = yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, width=4096,
        default_flow_style=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)  # first write for a new register
    path.write_text(header(dimension_slug, noun) + body)


def load_yaml(path: Path, where: str):
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise LinguaDataError(f"{where}: {exc}") from exc


def read_payload(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise LinguaDataError(f"cannot read payload {path}: {exc}") from exc
