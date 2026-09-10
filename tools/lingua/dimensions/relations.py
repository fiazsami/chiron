"""The concept-relations dimension: typed links between lexicon entries.

devenv/reference/<name>/<vN>/data/relations.yaml holds a flat edge list; each edge
links two lexicon slugs with a closed-set type, a one-line gloss, and
anchors. Both endpoints must exist in the lexicon, so a chapter's lexicon is
authored before its relations. Edges are keyed by (from, type, to): a second
chapter anchoring the same edge merges its anchors in (gloss is
last-writer-wins). A chapter whose anchored edge loses an endpoint counts as
stale — a dangling edge is drift even when hashes match.
"""

from pathlib import Path

from ..model import Chapter, Corpus
from . import base
from .base import LinguaDataError, SetContext

SLUG = "concept-relations"
LABEL = "Concept relations"
DATA_FILENAME = "relations.yaml"
METHODOLOGY = "methodology/concept-relations.md"
NOUN = "concept relations (typed links between terms)"

TYPES = (
    "is-a", "part-of", "uses", "feeds", "configures",
    "contrasts-with", "implements", "precedes",
)

MAX_EDGES_PER_PAYLOAD = 30
MAX_GLOSS_CHARS = 200

_EDGE_KEYS = {"from", "to", "type", "gloss", "anchors"}


def _key(edge: dict) -> tuple[str, str, str]:
    return (edge.get("from", ""), edge.get("type", ""), edge.get("to", ""))


def load(path: Path) -> dict:
    where = f"{DATA_FILENAME}"
    data = base.load_yaml(path, where)
    if data is None:
        return {"edges": []}
    if not isinstance(data, dict) or set(data) - {"edges"} \
            or not isinstance(data.get("edges"), list):
        raise LinguaDataError(f"{where}: expected a mapping with an 'edges' list")
    problems: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for i, edge in enumerate(data["edges"]):
        ew = f"{where} edges[{i}]"
        if not isinstance(edge, dict):
            problems.append(f"{ew}: expected a mapping")
            continue
        unknown = set(edge) - _EDGE_KEYS
        if unknown:
            problems.append(f"{ew}: unknown key(s): {', '.join(sorted(unknown))}")
        for end in ("from", "to"):
            if not isinstance(edge.get(end), str) \
                    or not base.SLUG_RE.fullmatch(edge.get(end, "")):
                problems.append(f"{ew}: '{end}' must be a lexicon slug")
        if edge.get("type") not in TYPES:
            problems.append(f"{ew}: 'type' must be one of {', '.join(TYPES)}")
        base.check_str(problems, ew, "gloss", edge.get("gloss"), MAX_GLOSS_CHARS)
        if _key(edge) in seen:
            problems.append(f"{ew}: duplicate edge {'/'.join(_key(edge))}")
        seen.add(_key(edge))
        anchors = edge.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            problems.append(f"{ew}: 'anchors' must be a non-empty list")
        else:
            for j, anchor in enumerate(anchors):
                problems += base.validate_stored_anchor(anchor, f"{ew}.anchors[{j}]")
    if problems:
        raise LinguaDataError("; ".join(problems))
    return data


def validate_payload(payload, ctx: SetContext) -> list[str]:
    """Return every violation in a `set concept-relations` payload."""
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be a JSON object with an 'edges' list"]
    unknown = set(payload) - {"edges"}
    if unknown:
        problems.append(f"unknown top-level key(s): {', '.join(sorted(unknown))}")
    edges = payload.get("edges")
    if not isinstance(edges, list) or not edges:
        problems.append("'edges' is required and must be a non-empty list")
        return problems
    if len(edges) > MAX_EDGES_PER_PAYLOAD:
        problems.append(f"{len(edges)} edges (max {MAX_EDGES_PER_PAYLOAD} per payload)")

    lexicon = ctx.data.get("lexicon", {})
    seen: set[tuple[str, str, str]] = set()
    for i, edge in enumerate(edges):
        where = f"edges[{i}]"
        if not isinstance(edge, dict):
            problems.append(f"{where}: must be an object")
            continue
        unknown = set(edge) - _EDGE_KEYS
        if unknown:
            problems.append(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
        for end in ("from", "to"):
            value = edge.get(end)
            if not isinstance(value, str) or not base.SLUG_RE.fullmatch(value):
                problems.append(f"{where}: '{end}' must be a lexicon slug")
            elif value not in lexicon:
                problems.append(
                    f"{where}: {end} term {value!r} is not in the lexicon — author "
                    f"the lexicon entry first (lexicon before relations)"
                )
        if isinstance(edge.get("from"), str) and edge.get("from") == edge.get("to"):
            problems.append(f"{where}: 'from' and 'to' must differ")
        if edge.get("type") not in TYPES:
            problems.append(f"{where}: 'type' must be one of {', '.join(TYPES)}")
        base.check_str(problems, where, "gloss", edge.get("gloss"), MAX_GLOSS_CHARS)
        if _key(edge) in seen:
            problems.append(f"{where}: duplicate edge {'/'.join(_key(edge))} in payload")
        seen.add(_key(edge))
        problems += base.validate_anchors(edge.get("anchors"), where, ctx)
    return problems


def apply(data: dict, ctx: SetContext, payload: dict) -> dict:
    """Merge a validated payload for ctx.chapter into the edge list."""
    local = ctx.chapter.local_id
    merged: dict[tuple[str, str, str], dict] = {}
    for edge in data.get("edges", []):
        kept = base.drop_chapter_anchors(edge.get("anchors", []), local)
        merged[_key(edge)] = {**edge, "anchors": kept}

    for edge in payload["edges"]:
        stamped = [base.stamp_anchor(a, ctx.chapter) for a in edge["anchors"]]
        key = _key(edge)
        kept = merged.get(key, {}).get("anchors", [])
        merged[key] = {
            "from": edge["from"],
            "to": edge["to"],
            "type": edge["type"],
            "gloss": edge["gloss"].strip(),
            "anchors": kept + stamped,
        }

    edges = [
        _canonical(edge) for key, edge in sorted(merged.items()) if edge["anchors"]
    ]
    return {"edges": edges}


def _canonical(edge: dict) -> dict:
    return {
        "from": edge["from"],
        "to": edge["to"],
        "type": edge["type"],
        "gloss": edge["gloss"],
        "anchors": sorted(
            edge["anchors"],
            key=lambda a: (a.get("chapter", ""), a.get("path", ""), a.get("quote", "")),
        ),
    }


def dump(path: Path, data: dict) -> None:
    base.dump_yaml(path, data, SLUG, NOUN)


def chapter_state(data: dict, chapter: Chapter, register_data: dict) -> str:
    lexicon = register_data.get("lexicon", {})
    mine = [
        edge for edge in data.get("edges", [])
        if any(a.get("chapter") == chapter.local_id for a in edge.get("anchors", []))
    ]
    if not mine:
        return "none"
    # A dangling endpoint is drift even when hashes match.
    if any(e.get("from") not in lexicon or e.get("to") not in lexicon for e in mine):
        return "stale"
    anchors = [a for e in mine for a in e.get("anchors", [])]
    return base.anchor_state(anchors, chapter)


def entries_for_chapter(data: dict, local_id: str) -> dict:
    return {
        "edges": [
            edge for edge in data.get("edges", [])
            if any(a.get("chapter") == local_id for a in edge.get("anchors", []))
        ]
    }


def accept_drift(data: dict, chapter: Chapter) -> int:
    return sum(
        base.repin_anchors(edge.get("anchors", []), chapter)
        for edge in data.get("edges", [])
    )


def count(data: dict) -> int:
    return len(data.get("edges", []))


def warnings(data: dict, corpus: Corpus, register_data: dict, where: str) -> list[str]:
    known = {c.local_id for c in corpus.chapters}
    out = base.orphan_warnings(
        {"/".join(_key(e)): e.get("anchors", []) for e in data.get("edges", [])},
        known, where,
    )
    lexicon = register_data.get("lexicon", {})
    for edge in data.get("edges", []):
        missing = sorted(
            {end for end in (edge.get("from"), edge.get("to")) if end not in lexicon}
        )
        if missing:
            out.append(
                f"{where} edge {'/'.join(_key(edge))} references term(s) no longer "
                f"in the lexicon: {', '.join(missing)}"
            )
    return out
