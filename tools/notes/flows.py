"""Load and validate the curated flow data, and compute per-chapter drift.

flows.yaml maps a chapter id ("foundations/06") to its curated flow lanes plus
component adjustments. Each entry records the content_hash it was curated
against; a mismatch marks the chapter "stale" until reviewed and accepted.
"""

import re
from pathlib import Path

import yaml

from .fingerprints import COMPONENTS
from .model import Chapter

FLOW_KINDS = {
    "input", "data", "process", "embed", "model", "store", "tool",
    "agent", "server", "guard", "decision", "output", "external",
}


class FlowDataError(Exception):
    pass


def load_flows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    for chapter_id, entry in data.items():
        where = f"flows.yaml entry {chapter_id!r}"
        if not isinstance(entry, dict):
            raise FlowDataError(f"{where}: expected a mapping")
        for key in ("components_extra", "components_suppress"):
            for comp in entry.get(key, []) or []:
                if comp not in COMPONENTS:
                    raise FlowDataError(f"{where}: unknown component {comp!r} in {key}")
        for lane in entry.get("flows", []) or []:
            steps = lane.get("steps", [])
            if not lane.get("name") or not steps:
                raise FlowDataError(f"{where}: each lane needs a name and steps")
            for step in steps:
                if step.get("kind") not in FLOW_KINDS:
                    raise FlowDataError(
                        f"{where}: lane {lane['name']!r} has unknown kind "
                        f"{step.get('kind')!r} (label {step.get('label')!r})"
                    )
                if not step.get("label"):
                    raise FlowDataError(f"{where}: lane {lane['name']!r} has a step without a label")
            for loop in lane.get("loops", []) or []:
                a, b = loop.get("from"), loop.get("to")
                if not (isinstance(a, int) and isinstance(b, int)
                        and 0 <= b < a < len(steps)):
                    raise FlowDataError(
                        f"{where}: lane {lane['name']!r} loop must satisfy "
                        f"0 <= to < from < {len(steps)} (got from={a}, to={b})"
                    )
    return data


def apply_flows(chapters: list[Chapter], flows: dict[str, dict], where: str) -> list[str]:
    """Attach curated entries to chapters and derive schematic_state; return
    warnings for orphan entries. `where` names the data file in warnings.

    Curation files are keyed by the register-local id ("foundations/06").

    States: a curated entry whose hash mismatches is "stale" even if it has no
    lanes (its component adjustments are stale too); a fresh entry with lanes
    is "ok"; without curated lanes the chapter's Mermaid is auto-converted
    ("fallback") when possible, else "none".
    """
    by_id = {chapter.local_id: chapter for chapter in chapters}
    for chapter in chapters:
        entry = flows.get(chapter.local_id)
        chapter.flow = entry
        chapter.fallback_flow = None
        if entry is not None:
            extra = set(entry.get("components_extra") or [])
            suppress = set(entry.get("components_suppress") or [])
            chapter.components = sorted(
                (set(chapter.detected_components) | extra) - suppress
            )
        else:
            chapter.components = chapter.detected_components

        if not (entry and entry.get("flows")) and chapter.mermaid:
            chapter.fallback_flow = flow_from_mermaid(chapter.mermaid)
        if entry is not None and entry.get("curated_against") != chapter.content_hash:
            chapter.schematic_state = "stale"
        elif entry is not None and entry.get("flows"):
            chapter.schematic_state = "ok"
        else:
            chapter.schematic_state = "fallback" if chapter.fallback_flow else "none"
    return [
        f"{where} entry {chapter_id!r} matches no current chapter (removed or renamed?)"
        for chapter_id in flows
        if chapter_id not in by_id
    ]


_MERMAID_REF = re.compile(
    r"^\s*(\w+)\s*(?:(\[\(|\(\[|\[\[|\[|\{|\()\s*\"?(.+?)\"?\s*(\)\]|\]\)|\]\]|\]|\}|\)))?\s*$"
)
_MERMAID_BRACKET_KINDS = {"[(": "store", "([": "input", "[[": "tool", "{": "decision"}


def flow_from_mermaid(mermaid: str) -> dict | None:
    """Best-effort conversion of a simple `A[x] --> B[y]` mermaid chain into a
    single linear lane. Returns None for anything non-linear (branches,
    bidirectional edges, subgraphs): the page then falls back to badges only.
    """
    labels: dict[str, tuple[str, str]] = {}
    edges: list[tuple[str, str]] = []

    def parse_ref(ref: str) -> str | None:
        m = _MERMAID_REF.match(ref)
        if not m:
            return None
        name, bracket, label = m.group(1), m.group(2), m.group(3)
        if label and name not in labels:
            kind = _MERMAID_BRACKET_KINDS.get(bracket, "process")
            if kind == "process" and "llm" in label.lower():
                kind = "model"
            labels[name] = (label, kind)
        return name

    for line in mermaid.splitlines():
        line = line.strip()
        if not line or line.startswith(("flowchart", "graph", "%%")):
            continue
        if "<-->" in line or "subgraph" in line or line == "end":
            return None
        if "-->" not in line:
            continue
        # Drop edge labels: -->|text| becomes -->
        line = re.sub(r"--?>\|[^|]*\|", "-->", line)
        refs = [r for r in (parse_ref(part) for part in line.split("-->")) if r]
        if len(refs) < 2:
            return None
        edges.extend(zip(refs, refs[1:]))

    if not edges:
        return None
    # Must be one simple path: unique successor/predecessor, single start node.
    succ: dict[str, str] = {}
    pred: dict[str, str] = {}
    for a, b in edges:
        if succ.get(a, b) != b or pred.get(b, a) != a:
            return None
        succ[a], pred[b] = b, a
    starts = [n for n in succ if n not in pred]
    if len(starts) != 1:
        return None
    chain = [starts[0]]
    while chain[-1] in succ:
        chain.append(succ[chain[-1]])
        if len(chain) > len(labels) + 1:
            return None  # cycle
    steps = []
    for name in chain:
        label, kind = labels.get(name, (name, "process"))
        steps.append({"label": label, "kind": kind})
    if steps:
        steps[0]["kind"] = "input" if steps[0]["kind"] == "process" else steps[0]["kind"]
        steps[-1]["kind"] = "output" if steps[-1]["kind"] == "process" else steps[-1]["kind"]
    return {"flows": [{"name": "Flow (from chapter diagram)", "steps": steps}]}


def accept_drift(path: Path, chapters: list[Chapter], ids: list[str]) -> list[str]:
    """Rewrite curated_against hashes in place (targeted line edits, preserving
    formatting and comments). ids are register-local chapter ids, or ["all"].
    Returns the full ids actually updated."""
    if not path.exists():  # nothing curated yet — nothing to re-pin
        return []
    by_local = {chapter.local_id: chapter for chapter in chapters}
    if ids == ["all"]:
        targets = [c.local_id for c in chapters if c.flow is not None and c.schematic_state == "stale"]
    else:
        unknown = [i for i in ids if i not in by_local]
        if unknown:
            raise FlowDataError(f"unknown chapter ids: {', '.join(unknown)}")
        targets = ids

    text = path.read_text()
    updated = []
    for local_id in targets:
        chapter = by_local[local_id]
        block_re = re.compile(
        rf"^({re.escape(local_id)}:\n(?:[ \t]+.*\n?)*?[ \t]+curated_against:[ \t]*)\"?[0-9a-f]*\"?",
            re.MULTILINE,
        )
        new_text, n = block_re.subn(rf'\g<1>"{chapter.content_hash}"', text)
        if n and new_text != text:
            text = new_text
            updated.append(chapter.id)
    path.write_text(text)
    return updated
