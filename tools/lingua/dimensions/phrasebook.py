"""The phrasebook dimension: how to say it when instructing an agent.

devenv/reference/<name>/<vN>/data/phrasebook.yaml maps a phrase slug to a canonical
phrasing (the collocation the corpus actually uses), the intent it serves, an
optional instruction template with {slots}, the lexicon terms it leans on,
and anchors. Phrases reference lexicon slugs, so a chapter's lexicon is
authored before its phrasebook. Writes are chapter-scoped with the same
drop-then-apply anchor semantics as the lexicon; phrase content is
last-writer-wins (the validator loop polices quality).
"""

from pathlib import Path

from ..model import Chapter, Corpus
from . import base
from .base import LinguaDataError, SetContext

SLUG = "phrasebook"
LABEL = "Phrasebook"
DATA_FILENAME = "phrasebook.yaml"
METHODOLOGY = "methodology/phrasebook.md"
NOUN = "phrasebook (canonical phrasings)"

MAX_PHRASES_PER_PAYLOAD = 15
MAX_PHRASE_CHARS = 160
MAX_INTENT_CHARS = 160
MAX_TEMPLATE_CHARS = 300

_ENTRY_KEYS = {"phrase", "intent", "template", "terms", "anchors"}
_PAYLOAD_KEYS = {"slug", "phrase", "intent", "template", "terms", "anchors"}


def load(path: Path) -> dict:
    where = f"{DATA_FILENAME}"
    data = base.load_yaml(path, where)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise LinguaDataError(f"{where}: expected a mapping of phrase slugs")
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
        base.check_str(problems, ew, "phrase", entry.get("phrase"), MAX_PHRASE_CHARS)
        base.check_str(problems, ew, "intent", entry.get("intent"), MAX_INTENT_CHARS)
        base.check_str(problems, ew, "template", entry.get("template"),
                       MAX_TEMPLATE_CHARS, required=False, single=False)
        terms = entry.get("terms")
        if not isinstance(terms, list) or not terms or not all(
            isinstance(t, str) and base.SLUG_RE.fullmatch(t) for t in terms
        ):
            problems.append(f"{ew}: 'terms' must be a non-empty list of lexicon slugs")
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
    """Return every violation in a `set phrasebook` payload."""
    problems: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be a JSON object with a 'phrases' list"]
    unknown = set(payload) - {"phrases"}
    if unknown:
        problems.append(f"unknown top-level key(s): {', '.join(sorted(unknown))}")
    phrases = payload.get("phrases")
    if not isinstance(phrases, list) or not phrases:
        problems.append("'phrases' is required and must be a non-empty list")
        return problems
    if len(phrases) > MAX_PHRASES_PER_PAYLOAD:
        problems.append(
            f"{len(phrases)} phrases (max {MAX_PHRASES_PER_PAYLOAD} per payload)"
        )

    lexicon = ctx.data.get("lexicon", {})
    seen: set[str] = set()
    for i, phrase in enumerate(phrases):
        where = f"phrases[{i}]"
        if not isinstance(phrase, dict):
            problems.append(f"{where}: must be an object")
            continue
        unknown = set(phrase) - _PAYLOAD_KEYS
        if unknown:
            problems.append(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
        slug = phrase.get("slug")
        if not isinstance(slug, str) or not base.SLUG_RE.fullmatch(slug):
            problems.append(f"{where}: 'slug' must match {base.SLUG_RE.pattern}")
        elif slug in seen:
            problems.append(f"{where}: duplicate slug {slug!r} in payload")
        else:
            seen.add(slug)
        base.check_str(problems, where, "phrase", phrase.get("phrase"), MAX_PHRASE_CHARS)
        base.check_str(problems, where, "intent", phrase.get("intent"), MAX_INTENT_CHARS)
        base.check_str(problems, where, "template", phrase.get("template"),
                       MAX_TEMPLATE_CHARS, required=False, single=False)
        terms = phrase.get("terms")
        if not isinstance(terms, list) or not terms:
            problems.append(f"{where}: 'terms' must be a non-empty list of lexicon slugs")
        else:
            for t in terms:
                if not isinstance(t, str) or t not in lexicon:
                    problems.append(
                        f"{where}: term {t!r} is not in the lexicon — author the "
                        f"lexicon entry first (lexicon before phrasebook)"
                    )
        problems += base.validate_anchors(phrase.get("anchors"), where, ctx)
    return problems


def apply(data: dict, ctx: SetContext, payload: dict) -> dict:
    """Merge a validated payload for ctx.chapter into the phrasebook."""
    local = ctx.chapter.local_id
    merged: dict[str, dict] = {}
    for slug, entry in data.items():
        kept = base.drop_chapter_anchors(entry.get("anchors", []), local)
        merged[slug] = {**entry, "anchors": kept}

    for phrase in payload["phrases"]:
        slug = phrase["slug"]
        stamped = [base.stamp_anchor(a, ctx.chapter) for a in phrase["anchors"]]
        kept = merged.get(slug, {}).get("anchors", [])
        entry = {
            "phrase": phrase["phrase"].strip(),
            "intent": phrase["intent"].strip(),
        }
        if phrase.get("template") and phrase["template"].strip():
            entry["template"] = phrase["template"].strip()
        entry["terms"] = list(phrase["terms"])
        entry["anchors"] = kept + stamped
        merged[slug] = entry

    merged = {slug: e for slug, e in merged.items() if e["anchors"]}
    return {slug: _canonical(merged[slug]) for slug in sorted(merged)}


def _canonical(entry: dict) -> dict:
    out = {"phrase": entry["phrase"], "intent": entry["intent"]}
    if entry.get("template"):
        out["template"] = entry["template"]
    out["terms"] = list(entry["terms"])
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


def accept_drift(data: dict, chapter: Chapter) -> int:
    return sum(
        base.repin_anchors(entry.get("anchors", []), chapter)
        for entry in data.values()
    )


def count(data: dict) -> int:
    return len(data)


def warnings(data: dict, corpus: Corpus, register_data: dict, where: str) -> list[str]:
    known = {c.local_id for c in corpus.chapters}
    out = base.orphan_warnings(
        {slug: e.get("anchors", []) for slug, e in data.items()}, known, where
    )
    lexicon = register_data.get("lexicon", {})
    for slug, entry in sorted(data.items()):
        missing = sorted(t for t in entry.get("terms", []) if t not in lexicon)
        if missing:
            out.append(
                f"{where} entry {slug!r} references term(s) no longer in the "
                f"lexicon: {', '.join(missing)}"
            )
    return out
