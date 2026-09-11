"""The evaluation surface: one entry, resolved whole, with both joins done.

`vocab` hands a reader every name a register uses so they can decide which
ones matter. This is the other half — it takes those slugs back and returns
what the register actually knows about them.

The joins are the point. A definition alone tells an unfamiliar reader what a
name means; it does not tell them what else they will need, or that the corpus
holds two of their requirements in opposition. Both facts are already in the
substrate and neither has ever reached a surface:

    phrases    — phrasebook entries whose `terms:` names this slug. These
                 carry `template:`, which is instruction scaffolding written
                 in the corpus's own words rather than paraphrased into them.
    relations  — every edge with this slug at either end. `uses`, `part-of`
                 and `configures` are what you will also need; `contrasts-with`
                 is where you are about to ask for two things this corpus
                 treats as alternatives, which is a design error worth
                 catching before an edit rather than after one.

Both joins are mechanical — a back-reference and a graph adjacency — so the
model in the loop makes exactly one judgement (which slugs matter) and the
tooling does the rest. That division is deliberate: it is the half of the
guardrail that cannot be wrong.

Read-only, like `vocab` and the study half.
"""

import json

from .status import RegisterBundle

# Anchors are capped and the joins are not, which looks inconsistent and is
# not. Anchors are repeated evidence for one claim — the fourth quote proving
# a definition tells a reader nothing the first three did. Every phrasing and
# every edge is a distinct fact, and dropping one silently would undercut the
# only thing this surface can honestly promise: that what it did not list, the
# register does not hold. The JSON is uncapped either way.
MAX_ANCHORS_SHOWN = 3

# Edges that say "instead of", separated from edges that say "along with".
# An unfamiliar reader needs the second; they need to be *stopped* by the first.
OPPOSING = "contrasts-with"


def parse_id(raw: str) -> tuple[str, str]:
    """(kind, slug). A bare slug is a term — that is what `vocab` prints, and
    a reader who copies one out of it should not have to decorate it."""
    kind, sep, slug = raw.partition(":")
    if not sep:
        return "term", raw
    if kind not in ("term", "phrase", "relation"):
        return "term", raw
    return kind, slug


def _phrases_naming(bundle: RegisterBundle, slug: str) -> list[dict]:
    """The phrasebook join: entries whose `terms:` back-reference this slug."""
    if "phrasebook" not in bundle.tracked_modes:
        return []
    return [
        {
            "id": f"phrase:{phrase_slug}",
            "phrase": data["phrase"],
            "intent": data["intent"],
            "template": data.get("template"),
            "terms": list(data.get("terms") or []),
        }
        for phrase_slug, data in sorted(bundle.data["phrasebook"].items())
        if slug in (data.get("terms") or [])
    ]


def _edges_touching(bundle: RegisterBundle, slug: str) -> list[dict]:
    """The relations join: every edge with this slug at either end, oriented
    so the reader can see which way the claim runs."""
    if "concept-relations" not in bundle.tracked_modes:
        return []
    out = []
    for edge in bundle.data["concept-relations"]["edges"]:
        if slug not in (edge["from"], edge["to"]):
            continue
        outgoing = edge["from"] == slug
        out.append({
            "id": f"relation:{edge['from']}--{edge['type']}--{edge['to']}",
            "from": edge["from"],
            "to": edge["to"],
            "type": edge["type"],
            "gloss": edge["gloss"],
            "other": edge["to"] if outgoing else edge["from"],
            "direction": "out" if outgoing else "in",
            "opposing": edge["type"] == OPPOSING,
        })
    out.sort(key=lambda e: (e["opposing"], e["type"], e["other"]))
    return out


def _anchors(raw: list[dict]) -> list[dict]:
    return [
        {
            "chapter": a["chapter"],
            "path": a.get("path"),
            "quote": a["quote"].strip(),
            "curated_against": a["curated_against"],
        }
        for a in raw
    ]


def resolve(bundle: RegisterBundle, raw_id: str) -> dict:
    """One entry's whole payload, joins included. `found: False` rather than
    an exception: a reader who mistyped one slug out of eight should still get
    the other seven."""
    kind, slug = parse_id(raw_id)
    base = {"input": raw_id, "kind": kind, "slug": slug, "found": False}

    if kind == "term":
        data = (bundle.data.get("lexicon") or {}).get(slug)
        if not data:
            return base
        return {
            **base,
            "found": True,
            "id": f"term:{slug}",
            "term": data["term"],
            "term_kind": data["kind"],
            "definition": data["definition"],
            "aliases": list(data.get("aliases") or []),
            "defined_in": data["defined_in"],
            "anchors": _anchors(data["anchors"]),
            "phrases": _phrases_naming(bundle, slug),
            "relations": _edges_touching(bundle, slug),
        }

    if kind == "phrase":
        data = (bundle.data.get("phrasebook") or {}).get(slug)
        if not data:
            return base
        return {
            **base,
            "found": True,
            "id": f"phrase:{slug}",
            "phrase": data["phrase"],
            "intent": data["intent"],
            "template": data.get("template"),
            "terms": list(data.get("terms") or []),
            "anchors": _anchors(data["anchors"]),
        }

    edges = [
        e for e in (bundle.data.get("concept-relations") or {}).get("edges", [])
        if f"{e['from']}--{e['type']}--{e['to']}" == slug
    ]
    if not edges:
        return base
    edge = edges[0]
    return {
        **base,
        "found": True,
        "id": f"relation:{slug}",
        "from": edge["from"],
        "to": edge["to"],
        "type": edge["type"],
        "gloss": edge["gloss"],
        "anchors": _anchors(edge["anchors"]),
    }


# --- rendering ---------------------------------------------------------------

def _anchor_lines(payload: dict, indent: str = "  ") -> list[str]:
    anchors = payload.get("anchors") or []
    out = []
    for anchor in anchors[:MAX_ANCHORS_SHOWN]:
        where = anchor["chapter"]
        if anchor.get("path"):
            where += f" · {anchor['path']}"
        out.append(f"{indent}evidence {where} @ {anchor['curated_against']}")
        out.append(f'{indent}          "{anchor["quote"]}"')
    extra = len(anchors) - MAX_ANCHORS_SHOWN
    if extra > 0:
        out.append(f"{indent}… {extra} more anchor(s)")
    return out


def lines(payload: dict) -> list[str]:
    if not payload["found"]:
        noun = {"term": "lexicon", "phrase": "phrasebook",
                "relation": "relations"}[payload["kind"]]
        return [f"{payload['input']} — not in this {noun}", ""]

    if payload["kind"] == "phrase":
        out = [f"{payload['phrase']}   {payload['id']}",
               f"  intent: {payload['intent']}"]
        if payload["template"]:
            out.append(f"  template: {payload['template']}")
        if payload["terms"]:
            out.append(f"  names: {', '.join(payload['terms'])}")
        return out + _anchor_lines(payload) + [""]

    if payload["kind"] == "relation":
        out = [f"{payload['from']} —{payload['type']}→ {payload['to']}   "
               f"{payload['id']}",
               f"  {payload['gloss']}"]
        return out + _anchor_lines(payload) + [""]

    out = [f"{payload['term']}   ({payload['term_kind']})   {payload['id']}",
           f"  {payload['definition']}"]
    if payload["aliases"]:
        out.append(f"  also called: {', '.join(payload['aliases'])}")
    out.append(f"  defined in {payload['defined_in']}")
    out += _anchor_lines(payload)

    phrases = payload["phrases"]
    if phrases:
        out += ["", f"  how to say it ({len(phrases)})"]
        for phrase in phrases:
            out.append(f"    {phrase['phrase']}   {phrase['id']}")
            out.append(f"      intent: {phrase['intent']}")
            if phrase["template"]:
                out.append(f"      template: {phrase['template']}")

    alongside = [e for e in payload["relations"] if not e["opposing"]]
    opposed = [e for e in payload["relations"] if e["opposing"]]
    if alongside:
        out += ["", f"  what else this touches ({len(alongside)})"]
        for edge in alongside:
            out.append(f"    {edge['from']} —{edge['type']}→ {edge['to']}")
            out.append(f"      {edge['gloss']}")
    if opposed:
        out += ["", f"  what this is an alternative to ({len(opposed)}) — "
                    f"asking for both is a design error, not a phrasing one"]
        for edge in opposed:
            out.append(f"    {edge['from']} —{edge['type']}→ {edge['to']}")
            out.append(f"      {edge['gloss']}")
    return out + [""]


def print_entries(bundle: RegisterBundle, raw_ids: list[str],
                  as_json: bool) -> int:
    payloads = [resolve(bundle, raw) for raw in raw_ids]
    if as_json:
        key = f"{bundle.corpus.name}/{bundle.corpus.register}"
        print(json.dumps(
            {"register": key, "entries": payloads}, indent=2))
    else:
        out: list[str] = []
        for payload in payloads:
            out += lines(payload)
        print("\n".join(out).rstrip())
    # Exit 1 when anything was missing, for the same reason `ask` exits 1 on a
    # substrate gap: a caller scripting this must be able to tell a silent
    # miss from a hit without parsing prose.
    return 0 if all(p["found"] for p in payloads) else 1
