"""The vocabulary index: every name a register uses, cheap enough to read whole.

`ask` and `grade` answer questions about a register. This answers the question
that comes before them — *is any of this relevant at all* — and it answers it
by handing over the whole list rather than by searching it.

That is a deliberate inversion. Searching a register for a prompt written by
someone who does not yet speak its language fails in both directions: nearest
neighbour returns lexical neighbours wearing a semantic costume, and the
`MIN_MATCH` floor that stops it returning confident nonsense also manufactures
false gaps — "nothing names that" for a question the corpus answers two entries
over. A false gap is the worst thing a guardrail can say, because it sends the
reader away from an answer that was there.

Reading the list has neither failure. A register's terms cost a few thousand
tokens (430 terms is ~5k), which is small enough to hold in context while
deciding relevance, and holding it in context is what makes the negative
answer defensible: "none of the 430 things this corpus names concern OAuth" is
auditable by the human, because the list is right there. "Retrieval scored
nothing above the floor" is not.

Read-only, like the rest of the study half. Output is grouped in the corpus's
own group order — structure the reader gets for free, and the first cut a
larger register would scope by.
"""

import json

from .status import RegisterBundle

UNGROUPED = "(ungrouped)"

# Reading the list is the point; a reader who searches it instead inherits
# every failure mode this module exists to avoid.
NOTE = ("read the whole list — a term is only absent when nothing here names "
        "it")


def _group_of(entry: dict) -> str:
    """The group a term was defined in. `defined_in` is `<group>/<NN>`, and a
    register whose chapters carry no group prefix has one flat namespace."""
    defined_in = entry.get("defined_in") or ""
    return defined_in.split("/")[0] if "/" in defined_in else UNGROUPED


def _redundant(slug: str, term: str) -> bool:
    """Whether the canonical term adds nothing the slug did not already say —
    `collector`/`Collector`, `type-builder`/`type builder`. Printing both
    doubles the width of a third of the list for no reader gain."""
    return slug.replace("-", " ").casefold() == term.replace("-", " ").casefold()


def terms(bundle: RegisterBundle) -> list[dict]:
    """Every term the register names, in group order then slug order."""
    if "lexicon" not in bundle.tracked_modes:
        return []
    data = bundle.data["lexicon"]
    order = {group.id: i for i, group in enumerate(bundle.corpus.groups)}
    out = [
        {
            "slug": slug,
            "term": entry["term"],
            "kind": entry["kind"],
            "aliases": list(entry.get("aliases") or []),
            "group": _group_of(entry),
            "defined_in": entry.get("defined_in") or "",
        }
        for slug, entry in data.items()
    ]
    # Groups the corpus declares come first, in its own order; anything else
    # (a chapter with no group, a group dropped from translation.yaml) sorts
    # after by name rather than vanishing.
    out.sort(key=lambda t: (order.get(t["group"], len(order)), t["group"],
                            t["slug"]))
    return out


def _line(entry: dict) -> str:
    parts = [entry["slug"]]
    if not _redundant(entry["slug"], entry["term"]):
        parts.append(f"— {entry['term']}")
    parts.append(f"({entry['kind']})")
    if entry["aliases"]:
        parts.append(f"aka {', '.join(entry['aliases'])}")
    return "  " + " ".join(parts)


def lines(bundle: RegisterBundle) -> list[str]:
    key = f"{bundle.corpus.name}/{bundle.corpus.register}"
    entries = terms(bundle)
    if "lexicon" not in bundle.tracked_modes:
        return [f"{key} — does not track lexicon; no vocabulary to read", ""]
    if not entries:
        return [f"{key} — no terms authored yet: "
                f"{cmd_hint(key)}", ""]

    labels = {group.id: group.label for group in bundle.corpus.groups}
    out = [f"{key} — {len(entries)} terms · {bundle.corpus.title}", NOTE, ""]
    current = None
    for entry in entries:
        if entry["group"] != current:
            current = entry["group"]
            label = labels.get(current, current)
            out.append(f"{current}" + (f"  ({label})" if label != current
                                       and current != UNGROUPED else ""))
        out.append(_line(entry))
    out.append("")
    return out


def cmd_hint(key: str) -> str:
    from .where import cmd
    return cmd(f"translate {key}")


def as_json(bundles: list[RegisterBundle]) -> list[dict]:
    return [
        {
            "register": f"{b.corpus.name}/{b.corpus.register}",
            "title": b.corpus.title,
            "tracks_lexicon": "lexicon" in b.tracked_modes,
            "count": len(terms(b)),
            "terms": terms(b),
        }
        for b in bundles
    ]


def print_vocab(bundles: list[RegisterBundle], as_json_out: bool) -> int:
    if as_json_out:
        print(json.dumps(as_json(bundles), indent=2))
        return 0
    out: list[str] = []
    for bundle in bundles:
        out += lines(bundle)
    print("\n".join(out).rstrip())
    return 0
