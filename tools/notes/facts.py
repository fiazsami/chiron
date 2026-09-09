"""Load, validate, and write the curated key-facts data (corpora/<name>/<vN>/data/facts.yaml).

facts.yaml maps a chapter id ("foundations/03") to its Cliff's-notes outline: a
required one-sentence takeaway plus sectioned bullet points, pinned to the
content_hash it was authored against (mismatch marks it "stale"). Unlike the
hand-formatted flows.yaml, this file is MACHINE-OWNED: entries are written only
through `--set-facts`, which validates the payload and re-emits the whole file
in canonical form (sorted by group/chapter, fixed key order), so diffs stay
stable and hand-editing is never needed.
"""

import json
import re
from pathlib import Path

import yaml

from .model import Chapter

MAX_SECTIONS = 8
MAX_POINTS_PER_SECTION = 6
MAX_TOTAL_POINTS = 30
MAX_HEADING_CHARS = 60
MAX_POINT_CHARS = 240
MAX_TAKEAWAY_CHARS = 200

_HEADER = """\
# Curated key facts ("Cliff's notes") per chapter of this corpus, keyed by
# "<group>/<chapter-number>". MACHINE-OWNED: written by
#   uv run python -m tools.notes --set-facts <id> --from <file.json>
# Do not hand-edit; the whole file is rewritten in canonical form on every
# write, and comments other than this header are not preserved.

"""

_NUMBER_RE = re.compile(r"^(\d+)([a-z]?)$")


class FactsDataError(Exception):
    pass


def _one_line(value: str) -> bool:
    return "\n" not in value and "\r" not in value


def validate_payload(obj) -> list[str]:
    """Return every schema violation in the payload (empty list = valid),
    so an authoring agent can fix everything in one revision."""
    problems: list[str] = []
    if not isinstance(obj, dict):
        return ["payload must be a JSON object with keys 'takeaway' and 'sections'"]
    unknown = set(obj) - {"takeaway", "sections"}
    if unknown:
        problems.append(f"unknown top-level key(s): {', '.join(sorted(unknown))}")

    takeaway = obj.get("takeaway")
    if not isinstance(takeaway, str) or not takeaway.strip():
        problems.append("'takeaway' is required and must be a non-empty string")
    elif not _one_line(takeaway):
        problems.append("'takeaway' must be a single line")
    elif len(takeaway) > MAX_TAKEAWAY_CHARS:
        problems.append(f"'takeaway' is {len(takeaway)} chars (max {MAX_TAKEAWAY_CHARS})")

    sections = obj.get("sections")
    if not isinstance(sections, list) or not sections:
        problems.append("'sections' is required and must be a non-empty list")
        return problems
    if len(sections) > MAX_SECTIONS:
        problems.append(f"{len(sections)} sections (max {MAX_SECTIONS})")

    total_points = 0
    for i, sec in enumerate(sections):
        where = f"sections[{i}]"
        if not isinstance(sec, dict):
            problems.append(f"{where}: must be an object with 'heading' and 'points'")
            continue
        unknown = set(sec) - {"heading", "points"}
        if unknown:
            problems.append(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
        heading = sec.get("heading")
        if not isinstance(heading, str) or not heading.strip():
            problems.append(f"{where}: 'heading' must be a non-empty string")
        elif not _one_line(heading):
            problems.append(f"{where}: 'heading' must be a single line")
        elif len(heading) > MAX_HEADING_CHARS:
            problems.append(f"{where}: heading is {len(heading)} chars (max {MAX_HEADING_CHARS})")
        points = sec.get("points")
        if not isinstance(points, list) or not points:
            problems.append(f"{where}: 'points' must be a non-empty list")
            continue
        if len(points) > MAX_POINTS_PER_SECTION:
            problems.append(f"{where}: {len(points)} points (max {MAX_POINTS_PER_SECTION})")
        total_points += len(points)
        for j, point in enumerate(points):
            if not isinstance(point, str) or not point.strip():
                problems.append(f"{where}.points[{j}]: must be a non-empty string")
            elif not _one_line(point):
                problems.append(f"{where}.points[{j}]: must be a single line")
            elif len(point) > MAX_POINT_CHARS:
                problems.append(
                    f"{where}.points[{j}]: {len(point)} chars (max {MAX_POINT_CHARS})"
                )
    if total_points > MAX_TOTAL_POINTS:
        problems.append(f"{total_points} points across sections (max {MAX_TOTAL_POINTS})")
    return problems


def load_facts(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    problems: list[str] = []
    for chapter_id, entry in data.items():
        where = f"facts.yaml entry {chapter_id!r}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: expected a mapping")
            continue
        hash_ = entry.get("curated_against")
        if not isinstance(hash_, str) or not re.fullmatch(r"[0-9a-f]{12}", hash_):
            problems.append(f"{where}: 'curated_against' must be a 12-hex content hash")
        payload = {k: v for k, v in entry.items() if k != "curated_against"}
        problems += [f"{where}: {p}" for p in validate_payload(payload)]
    if problems:
        raise FactsDataError("; ".join(problems))
    return data


def apply_facts(chapters: list[Chapter], facts: dict[str, dict], where: str) -> list[str]:
    """Attach curated facts to chapters and derive facts_state; return warnings
    for orphan entries. `where` names the data file in warnings. Curation
    files are keyed by the register-local id ("foundations/03")."""
    by_id = {chapter.local_id: chapter for chapter in chapters}
    for chapter in chapters:
        entry = facts.get(chapter.local_id)
        chapter.facts = entry
        if entry is None:
            chapter.facts_state = "none"
        elif entry.get("curated_against") == chapter.content_hash:
            chapter.facts_state = "ok"
        else:
            chapter.facts_state = "stale"
    return [
        f"{where} entry {chapter_id!r} matches no current chapter (removed or renamed?)"
        for chapter_id in facts
        if chapter_id not in by_id
    ]


def _sort_key(chapter_id: str, group_order: list[str]) -> tuple:
    group, _, number = chapter_id.partition("/")
    m = _NUMBER_RE.match(number)
    group_rank = group_order.index(group) if group in group_order else len(group_order)
    return (group_rank, int(m.group(1)) if m else 0, m.group(2) if m else number)


def _dump(path: Path, data: dict[str, dict], group_order: list[str]) -> None:
    body = yaml.safe_dump(
        {k: data[k] for k in sorted(data, key=lambda k: _sort_key(k, group_order))},
        sort_keys=False, allow_unicode=True, width=4096, default_flow_style=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)  # first write for a new corpus
    path.write_text(_HEADER + body)


def set_facts(path: Path, chapter: Chapter, payload: dict, group_order: list[str]) -> None:
    """Insert or replace the chapter's entry, pinned to its current content
    hash. The payload must already have passed validate_payload."""
    data = load_facts(path)
    data[chapter.local_id] = {
        "curated_against": chapter.content_hash,
        "takeaway": payload["takeaway"],
        "sections": [
            {"heading": s["heading"], "points": list(s["points"])}
            for s in payload["sections"]
        ],
    }
    _dump(path, data, group_order)


def read_payload(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise FactsDataError(f"cannot read payload {path}: {exc}") from exc


def accept_drift(
    path: Path, chapters: list[Chapter], ids: list[str], group_order: list[str]
) -> list[str]:
    """Re-pin curated_against for stale facts entries. ids are register-local
    chapter ids, or ["all"] (every currently-stale entry). Ids without a facts
    entry are skipped. Returns the full ids actually updated. Prefer
    re-authoring via /update-notes over accepting drift blind: this re-blesses
    content as-is."""
    data = load_facts(path)
    by_local = {chapter.local_id: chapter for chapter in chapters}
    if ids == ["all"]:
        targets = [c.local_id for c in chapters if c.facts is not None and c.facts_state == "stale"]
    else:
        unknown = [i for i in ids if i not in by_local]
        if unknown:
            raise FactsDataError(f"unknown chapter ids: {', '.join(unknown)}")
        targets = [i for i in ids if i in data]
    updated = []
    for local_id in targets:
        if data[local_id]["curated_against"] != by_local[local_id].content_hash:
            data[local_id]["curated_against"] = by_local[local_id].content_hash
            updated.append(by_local[local_id].id)
    if updated:
        _dump(path, data, group_order)
    return updated
