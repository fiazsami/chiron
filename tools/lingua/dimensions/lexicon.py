"""The lexicon dimension: what things are called in this corpus.

corpora/<name>/<vN>/data/lexicon.yaml maps a term slug to its canonical
surface form, kind, grounded definition, and anchors. Terms are corpus-scoped
(one entry per concept, however many chapters mention it); writes are
chapter-scoped — a payload for chapter C first drops C's anchors everywhere,
then applies, so re-authoring a chapter is idempotent and removals work. The
chapter that defines a term owns its definition (`defined_in`); redefining it
from another chapter requires --redefine.
"""

from pathlib import Path

from ..model import Chapter, Corpus
from . import base
from .base import LinguaDataError, SetContext

SLUG = "lexicon"
LABEL = "Lexicon"
DATA_FILENAME = "lexicon.yaml"
METHODOLOGY = "methodology/lexicon.md"
NOUN = "lexicon (terms, names, identifiers)"

KINDS = ("concept", "name", "identifier", "command", "file", "value")

MAX_TERMS_PER_PAYLOAD = 40
MAX_TERMS_PER_FILE = 500
MAX_TERM_CHARS = 80
MAX_DEFINITION_CHARS = 400
MAX_ALIASES = 6

_ENTRY_KEYS = {"term", "kind", "definition", "aliases", "defined_in", "anchors"}
_PAYLOAD_TERM_KEYS = {"slug", "term", "kind", "definition", "aliases", "define", "anchors"}


def load(path: Path) -> dict:
    where = f"{DATA_FILENAME}"
    data = base.load_yaml(path, where)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise LinguaDataError(f"{where}: expected a mapping of term slugs")
    problems: list[str] = []
    for slug, entry in data.items():
        ew = f"{where} entry {slug!r}"
        if not base.SLUG_RE.fullmatch(str(slug)):
            problems.append(f"{ew}: slug must match {base.SLUG_RE.pattern}")
        if not isinstance(entry, dict):
            problems.append(f"{ew}: expected a mapping")
            continue
        unknown = set(entry) - _ENTRY_KEYS
        if unknown:
            problems.append(f"{ew}: unknown key(s): {', '.join(sorted(unknown))}")
        base.check_str(problems, ew, "term", entry.get("term"), MAX_TERM_CHARS)
        if entry.get("kind") not in KINDS:
            problems.append(f"{ew}: 'kind' must be one of {', '.join(KINDS)}")
        base.check_str(problems, ew, "definition", entry.get("definition"),
                       MAX_DEFINITION_CHARS, single=False)
        aliases = entry.get("aliases")
        if aliases is not None:
            if not isinstance(aliases, list) or len(aliases) > MAX_ALIASES:
                problems.append(f"{ew}: 'aliases' must be a list of at most {MAX_ALIASES}")
            else:
                for i, alias in enumerate(aliases):
                    base.check_str(problems, ew, f"aliases[{i}]", alias, MAX_TERM_CHARS)
        if not isinstance(entry.get("defined_in"), str) or not entry["defined_in"]:
            problems.append(f"{ew}: 'defined_in' must be a chapter id string")
        anchors = entry.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            problems.append(f"{ew}: 'anchors' must be a non-empty list")
        else:
            for i, anchor in enumerate(anchors):
                problems += base.validate_stored_anchor(anchor, f"{ew}.anchors[{i}]")
    if problems:
        raise LinguaDataError("; ".join(problems))
    return data


def validate_payload(payload, ctx: SetContext) -> list[str]:
    """Return every violation in a `set lexicon` payload (empty list = valid),
    so an authoring agent can fix everything in one revision."""
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be a JSON object with a 'terms' list"]
    unknown = set(payload) - {"terms"}
    if unknown:
        problems.append(f"unknown top-level key(s): {', '.join(sorted(unknown))}")
    terms = payload.get("terms")
    if not isinstance(terms, list) or not terms:
        problems.append("'terms' is required and must be a non-empty list")
        return problems
    if len(terms) > MAX_TERMS_PER_PAYLOAD:
        problems.append(f"{len(terms)} terms (max {MAX_TERMS_PER_PAYLOAD} per payload)")

    existing = ctx.data.get(SLUG, {})
    local = ctx.chapter.local_id
    seen: set[str] = set()
    for i, term in enumerate(terms):
        where = f"terms[{i}]"
        if not isinstance(term, dict):
            problems.append(f"{where}: must be an object")
            continue
        unknown = set(term) - _PAYLOAD_TERM_KEYS
        if unknown:
            problems.append(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
        slug = term.get("slug")
        if not isinstance(slug, str) or not base.SLUG_RE.fullmatch(slug):
            problems.append(f"{where}: 'slug' must match {base.SLUG_RE.pattern}")
            slug = None
        elif slug in seen:
            problems.append(f"{where}: duplicate slug {slug!r} in payload")
        else:
            seen.add(slug)
        define = term.get("define")
        if not isinstance(define, bool):
            problems.append(f"{where}: 'define' is required and must be true or false")
            define = None
        if define:
            base.check_str(problems, where, "term", term.get("term"), MAX_TERM_CHARS)
            if term.get("kind") not in KINDS:
                problems.append(f"{where}: 'kind' must be one of {', '.join(KINDS)}")
            base.check_str(problems, where, "definition", term.get("definition"),
                           MAX_DEFINITION_CHARS, single=False)
            aliases = term.get("aliases")
            if aliases is not None:
                if not isinstance(aliases, list) or len(aliases) > MAX_ALIASES:
                    problems.append(
                        f"{where}: 'aliases' must be a list of at most {MAX_ALIASES}"
                    )
                else:
                    for j, alias in enumerate(aliases):
                        base.check_str(problems, where, f"aliases[{j}]", alias,
                                       MAX_TERM_CHARS)
            if slug and slug in existing and existing[slug]["defined_in"] != local \
                    and not ctx.redefine:
                problems.append(
                    f"{where}: {slug!r} is defined by chapter "
                    f"{existing[slug]['defined_in']} — redefining it from {local} "
                    f"requires --redefine"
                )
        elif define is False:
            for key in ("term", "kind", "definition", "aliases"):
                if key in term:
                    problems.append(
                        f"{where}: '{key}' is only allowed with define: true "
                        f"(mention-only entries just add anchors)"
                    )
            if slug and slug not in existing:
                problems.append(
                    f"{where}: {slug!r} is not in the lexicon — mention-only "
                    f"entries need an existing term (or set define: true)"
                )
        problems += base.validate_anchors(term.get("anchors"), where, ctx)
    return problems


def apply(data: dict, ctx: SetContext, payload: dict) -> dict:
    """Merge a validated payload for ctx.chapter into the lexicon. Returns the
    new data mapping, sorted by slug with canonical key order."""
    local = ctx.chapter.local_id
    merged: dict[str, dict] = {}
    for slug, entry in data.items():
        kept = base.drop_chapter_anchors(entry.get("anchors", []), local)
        merged[slug] = {**entry, "anchors": kept}

    for term in payload["terms"]:
        slug = term["slug"]
        stamped = [base.stamp_anchor(a, ctx.chapter) for a in term["anchors"]]
        if term["define"]:
            kept = merged.get(slug, {}).get("anchors", [])
            entry = {
                "term": term["term"].strip(),
                "kind": term["kind"],
                "definition": term["definition"].strip(),
            }
            aliases = [a.strip() for a in term.get("aliases") or []]
            if aliases:
                entry["aliases"] = aliases
            entry["defined_in"] = local
            entry["anchors"] = kept + stamped
            merged[slug] = entry
        else:
            merged[slug]["anchors"] = merged[slug]["anchors"] + stamped

    # Entries that lost every anchor have no grounding left — drop them.
    merged = {slug: e for slug, e in merged.items() if e["anchors"]}
    if len(merged) > MAX_TERMS_PER_FILE:
        raise LinguaDataError(
            f"lexicon would have {len(merged)} terms (max {MAX_TERMS_PER_FILE})"
        )
    return {slug: _canonical(merged[slug]) for slug in sorted(merged)}


def _canonical(entry: dict) -> dict:
    out = {"term": entry["term"], "kind": entry["kind"],
           "definition": entry["definition"]}
    if entry.get("aliases"):
        out["aliases"] = list(entry["aliases"])
    out["defined_in"] = entry["defined_in"]
    out["anchors"] = sorted(
        entry["anchors"],
        key=lambda a: (a.get("chapter", ""), a.get("path", ""), a.get("quote", "")),
    )
    return out


def dump(path: Path, data: dict) -> None:
    base.dump_yaml(path, data, SLUG, NOUN)


def chapter_state(data: dict, chapter: Chapter, register_data: dict) -> str:
    anchors = [a for e in data.values() for a in e.get("anchors", [])]
    return base.anchor_state(anchors, chapter)


def entries_for_chapter(data: dict, local_id: str) -> dict:
    return {
        slug: entry
        for slug, entry in data.items()
        if any(a.get("chapter") == local_id for a in entry.get("anchors", []))
    }


def terms_defined(data: dict, local_id: str) -> list[str]:
    return sorted(s for s, e in data.items() if e.get("defined_in") == local_id)


def terms_mentioned(data: dict, local_id: str) -> list[str]:
    return sorted(
        slug for slug, entry in data.items()
        if entry.get("defined_in") != local_id
        and any(a.get("chapter") == local_id for a in entry.get("anchors", []))
    )


def slug_index(data: dict) -> list[str]:
    """One line per term — the cross-chapter device that keeps authors reusing
    slugs instead of forking them."""
    return [
        f"{slug}: {entry['term']} ({entry['kind']})"
        for slug, entry in sorted(data.items())
    ]


def accept_drift(data: dict, chapter: Chapter) -> int:
    return sum(
        base.repin_anchors(entry.get("anchors", []), chapter)
        for entry in data.values()
    )


def count(data: dict) -> int:
    return len(data)


def warnings(data: dict, corpus: Corpus, register_data: dict, where: str) -> list[str]:
    known = {c.local_id for c in corpus.chapters}
    return base.orphan_warnings(
        {slug: e.get("anchors", []) for slug, e in data.items()}, known, where
    )
