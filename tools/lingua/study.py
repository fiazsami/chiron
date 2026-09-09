"""The study half: what is this called here, and does my instruction land.

The methodology names three questions the substrate answers — what is this
called here, how do I say it when instructing an agent, how do the names
relate — and one goal: transfer, "the learner prompts any agent about this
corpus in its own terms without looking anything up". Production
(mount/translate) builds the substrate; this module is what a learner uses it
for.

Two commands, both read-only against `data/*.yaml`:

    ./ch ask   <register> ["<text>"]     lookup, or the load-bearing entries
    ./ch grade <register> --text "…"     coverage of one instruction

`grade` is the load-bearing one. It reports COVERAGE, not style: which parts
of an instruction name something this corpus actually names, and which parts
the agent would have to guess at. Its verdict is an exit code — 0 lands,
1 drifts — for the same reason `set` rejects a quote it cannot find:
grounding is enforced by the tooling, not by good intentions. The coach in
/ch:calibrate may explain a verdict; it may not overturn one.

A register's chroma store, when it exists, is a ranking accelerator for `ask`
and nothing more. Everything here works with zero optional dependencies, over
the same documents `chroma.build_bits` produces — study must not be gated
behind a first-run model download on precisely the fresh mounts that need it.
"""

import json
import re
import time
from pathlib import Path

from .chroma import build_bits, query_bits
from .dimensions.base import LinguaDataError
from .status import RegisterBundle
from .where import cmd

MAX_NGRAM = 4
MIN_MATCH = 0.2
DEFAULT_N = 6

# Function words carry no corpus vocabulary; a drift report that flags "the"
# is noise, not a finding.
STOPWORDS = frozenset("""
a an the this that these those it its his her their our your my
and or but so then than as if when while because for to of in on at by with
from into onto over under after before during about across via
is are was were be been being am do does did doing done have has had having
can could should would will shall may might must
i you he she we they me him them us
not no nor only just also very more most much many few some any all each
what which who whom whose how why where
one two three new old same other another next last
""".split())


def calibration_log(bundle: RegisterBundle) -> Path:
    return bundle.data_dir.parent / "work" / "calibration.jsonl"


def _chroma_dir(bundle: RegisterBundle) -> Path:
    return bundle.data_dir.parent / "chroma"


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9_.-]*", text.lower())


def _norm(text: str) -> str:
    return " ".join(_words(text))


# --- the entry index ---------------------------------------------------------

def index(bundle: RegisterBundle) -> list[dict]:
    """Every addressable entry of the register — one term, one phrasing, or
    one relation edge — with the document text an ask/grade match scores
    against. `entry` is the word the methodology already uses; the viewer's
    `bit` is the same thing under a name that never got ratified."""
    ids, docs, metas = build_bits(bundle)
    return [
        {"id": i, "document": d, "meta": m, "tokens": set(_words(d))}
        for i, d, m in zip(ids, docs, metas)
    ]


def surface_forms(bundle: RegisterBundle) -> dict[str, tuple[str, str]]:
    """Normalized surface form -> (entry id, why it matched). Every spelling
    the corpus itself offers: canonical terms, their aliases (the substrate
    has stored these since day one and nothing has ever read them), slugs,
    and phrasings."""
    out: dict[str, tuple[str, str]] = {}

    def put(text: str, entry_id: str, why: str) -> None:
        key = _norm(text)
        if key and key not in out:
            out[key] = (entry_id, why)

    if "lexicon" in bundle.tracked_modes:
        for slug, entry in bundle.data["lexicon"].items():
            put(entry["term"], f"term:{slug}", "canonical form")
            put(slug.replace("-", " "), f"term:{slug}", "slug")
            for alias in entry.get("aliases") or []:
                put(alias, f"term:{slug}", "alias")
    if "phrasebook" in bundle.tracked_modes:
        for slug, entry in bundle.data["phrasebook"].items():
            put(entry["phrase"], f"phrase:{slug}", "phrasing")
            put(slug.replace("-", " "), f"phrase:{slug}", "slug")
    return out


def _idf(entries: list[dict]) -> dict[str, float]:
    from math import log
    total = max(len(entries), 1)
    counts: dict[str, int] = {}
    for entry in entries:
        for token in entry["tokens"]:
            counts[token] = counts.get(token, 0) + 1
    return {t: log(total / c) + 1.0 for t, c in counts.items()}


def rank(entries: list[dict], text: str, n: int) -> list[tuple[float, dict]]:
    """Lexical ranking — deterministic, dependency-free, and good enough for
    the short queries study actually makes."""
    idf = _idf(entries)
    query = [t for t in _words(text) if t not in STOPWORDS]
    if not query:
        return []
    scored = []
    for entry in entries:
        overlap = [t for t in query if t in entry["tokens"]]
        if not overlap:
            continue
        score = sum(idf.get(t, 1.0) for t in overlap) / sum(
            idf.get(t, 1.0) for t in query)
        scored.append((round(score, 2), entry))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return scored[:n]


# --- rendering ---------------------------------------------------------------

def _entry_lines(bundle: RegisterBundle, entry_id: str, indent: str = "") -> list[str]:
    """One entry, rendered with the provenance the substrate has always
    carried and no surface has ever shown: the defining chapter and the
    content hash each anchor is pinned to."""
    kind, _, slug = entry_id.partition(":")
    out: list[str] = []
    if kind == "term":
        data = bundle.data["lexicon"].get(slug)
        if not data:
            return [f"{indent}{entry_id} — not in this lexicon"]
        out.append(f"{indent}{data['term']}   ({data['kind']})   {entry_id}")
        out.append(f"{indent}  {data['definition']}")
        if data.get("aliases"):
            out.append(f"{indent}  also called: {', '.join(data['aliases'])}")
        chapters = sorted({a["chapter"] for a in data["anchors"]})
        line = f"{indent}  defined in {data['defined_in']}"
        others = [c for c in chapters if c != data["defined_in"]]
        if others:
            line += f" · also anchored in {', '.join(others)}"
        out.append(line)
        anchors = data["anchors"]
    elif kind == "phrase":
        data = bundle.data["phrasebook"].get(slug)
        if not data:
            return [f"{indent}{entry_id} — not in this phrasebook"]
        out.append(f"{indent}{data['phrase']}   {entry_id}")
        out.append(f"{indent}  intent: {data['intent']}")
        if data.get("template"):
            out.append(f"{indent}  template: {data['template']}")
        if data.get("terms"):
            out.append(f"{indent}  names: {', '.join(data['terms'])}")
        anchors = data["anchors"]
    else:
        edges = [
            e for e in bundle.data["concept-relations"]["edges"]
            if f"{e['from']}--{e['type']}--{e['to']}" == slug
        ]
        if not edges:
            return [f"{indent}{entry_id} — no such edge"]
        edge = edges[0]
        out.append(f"{indent}{edge['from']} —{edge['type']}→ {edge['to']}"
                   f"   {entry_id}")
        out.append(f"{indent}  {edge['gloss']}")
        anchors = edge["anchors"]
    if anchors:
        first = anchors[0]
        out.append(f"{indent}  evidence {first['chapter']} "
                   f"@ {first['curated_against']}")
        out.append(f'{indent}            "{first["quote"].strip()}"')
    return out


# --- ask ---------------------------------------------------------------------

def ask(bundle: RegisterBundle, text: str | None, n: int,
        relate: tuple[str, str] | None, as_json: bool) -> int:
    entries = index(bundle)
    if not entries:
        raise LinguaDataError(
            f"{bundle.corpus.name}/{bundle.corpus.register} has no entries yet "
            f"— author some first: /ch:translate "
            f"{bundle.corpus.name}/{bundle.corpus.register}")

    if relate:
        return _relate(bundle, relate, as_json)

    if not text:
        # No query is a defined behaviour, not an error: the load-bearing
        # entries, which double as the drill pool.
        ranked = sorted(
            (e for e in entries if e["meta"]["kind"] == "term"),
            key=lambda e: (-len(e["meta"]["chapters"].split(", ")), e["id"]),
        )[:n]
        if as_json:
            print(json.dumps([e["id"] for e in ranked], indent=2))
            return 0
        print(f"{bundle.corpus.name}/{bundle.corpus.register} — the "
              f"load-bearing terms (widest anchor coverage):\n")
        for entry in ranked:
            for line in _entry_lines(bundle, entry["id"], "  "):
                print(line)
            print()
        return 0

    store = _chroma_dir(bundle)
    hits: list[tuple[float, dict]] = []
    if (store / "chroma.sqlite3").exists():
        try:
            by_id = {e["id"]: e for e in entries}
            hits = [
                (score, by_id[hit["id"]])
                for hit in query_bits(store, text, n) if hit["id"] in by_id
                # Nearest-neighbour search always returns neighbours. Without
                # a floor a question the corpus cannot answer comes back with
                # confident nonsense, and the substrate-gap path never fires.
                for score in [round(1.0 - hit["distance"], 2)]
                if score >= MIN_MATCH
            ]
        except Exception:
            hits = []  # the store is an accelerator, never a dependency
    if not hits:
        hits = [(s, e) for s, e in rank(entries, text, n) if s >= MIN_MATCH]

    if as_json:
        print(json.dumps([{"id": e["id"], "score": s} for s, e in hits], indent=2))
        return 0
    if not hits:
        print(f"nothing in {bundle.corpus.name}/{bundle.corpus.register} "
              f"names that.")
        print(f"that is a substrate gap, not a wrong question — if the corpus "
              f"does discuss it, author the chapter: /ch:translate "
              f"{bundle.corpus.name}/{bundle.corpus.register}")
        return 1
    for score, entry in hits:
        for line in _entry_lines(bundle, entry["id"], "  "):
            print(line)
        print(f"    match {score}")
        print()
    return 0


def _relate(bundle: RegisterBundle, pair: tuple[str, str], as_json: bool) -> int:
    """How two names relate — a shortest path over the typed edges."""
    if "concept-relations" not in bundle.tracked_modes:
        raise LinguaDataError(
            "this register does not track concept-relations")
    edges = bundle.data["concept-relations"]["edges"]
    start, goal = pair
    adjacency: dict[str, list[tuple[str, dict, bool]]] = {}
    for edge in edges:
        adjacency.setdefault(edge["from"], []).append((edge["to"], edge, True))
        adjacency.setdefault(edge["to"], []).append((edge["from"], edge, False))
    queue: list[tuple[str, list]] = [(start, [])]
    seen = {start}
    while queue:
        node, path = queue.pop(0)
        if node == goal:
            if as_json:
                print(json.dumps([
                    {"from": e["from"], "type": e["type"], "to": e["to"],
                     "gloss": e["gloss"]} for e, _ in path], indent=2))
                return 0
            if not path:
                print(f"{start} and {goal} are the same term.")
                return 0
            print(f"{start} → {goal}, {len(path)} edge(s):\n")
            for edge, forward in path:
                arrow = "—{}→".format(edge["type"]) if forward \
                    else "←{}—".format(edge["type"])
                print(f"  {edge['from']} {arrow} {edge['to']}")
                print(f"    {edge['gloss']}")
                if edge.get("anchors"):
                    a = edge["anchors"][0]
                    print(f"    evidence {a['chapter']} @ {a['curated_against']}")
            return 0
        for nxt, edge, forward in adjacency.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, path + [(edge, forward)]))
    print(f"no path between {start!r} and {goal!r} in this register's "
          f"relation graph.")
    return 1


# --- grade -------------------------------------------------------------------

def coverage(bundle: RegisterBundle, text: str) -> dict:
    """Which parts of an instruction this corpus actually names.

    Longest-match first over 1..4-grams against every surface form the corpus
    offers. What is left over, minus function words, is drift: each run is a
    place an agent would have to guess, and every guess is a place to be
    wrong."""
    forms = surface_forms(bundle)
    entries = index(bundle)
    tokens = _words(text)
    taken = [False] * len(tokens)
    land: list[dict] = []
    for size in range(min(MAX_NGRAM, len(tokens)), 0, -1):
        for i in range(0, len(tokens) - size + 1):
            if any(taken[i:i + size]):
                continue
            gram = " ".join(tokens[i:i + size])
            hit = forms.get(gram)
            if hit is None:
                continue
            entry_id, why = hit
            land.append({"text": gram, "id": entry_id, "why": why})
            for j in range(i, i + size):
                taken[j] = True

    drift: list[dict] = []
    run: list[str] = []

    def flush() -> None:
        # Function words may sit inside a drift run but never at its edges:
        # "stores the history" is one thing the corpus doesn't name, not two.
        while run and run[0] in STOPWORDS:
            run.pop(0)
        while run and run[-1] in STOPWORDS:
            run.pop()
        if not run:
            return
        phrase = " ".join(run)
        nearest = [
            {"id": e["id"], "score": score}
            for score, e in rank(entries, phrase, 2)
            # A one-word query trivially scores 1.0 against anything sharing
            # that word; only offer a nearest entry when the match is
            # specific enough to be worth the learner's attention.
            if score >= 0.5 and len(phrase.split()) > 1
        ]
        drift.append({"text": phrase, "nearest": nearest})
        run.clear()

    for i, token in enumerate(tokens):
        if taken[i]:
            flush()
            continue
        run.append(token)
    flush()
    return {"land": land, "drift": drift, "tokens": len(tokens)}


def _covering_phrasings(bundle: RegisterBundle, land: list[dict]) -> list[str]:
    """Phrasings that already name what the learner is reaching for."""
    if "phrasebook" not in bundle.tracked_modes:
        return []
    named = {h["id"].split(":", 1)[1] for h in land if h["id"].startswith("term:")}
    out = []
    for slug, entry in bundle.data["phrasebook"].items():
        if named & set(entry.get("terms") or []):
            out.append(f"phrase:{slug}")
    return out[:5]


def grade(bundle: RegisterBundle, text: str, against: str | None,
          as_json: bool, log: bool) -> int:
    result = coverage(bundle, text)
    land, drift = result["land"], result["drift"]
    key = f"{bundle.corpus.name}/{bundle.corpus.register}"

    if against:
        # Drill mode: one target entry, hit or miss, no partial credit.
        hit = any(h["id"] == against for h in land)
        if as_json:
            print(json.dumps({"verdict": "hit" if hit else "miss",
                              "against": against, "land": land}, indent=2))
        else:
            print(f"  target   {against}")
            for line in _entry_lines(bundle, against, "  "):
                print(line)
            print(f"  you said \"{text}\"")
            if hit:
                print("  hit      you used the corpus's own form")
            else:
                nearest = rank(index(bundle), text, 1)
                near = f" — nearest {nearest[0][1]['id']} ({nearest[0][0]})" \
                    if nearest else ""
                print(f"  miss     not the canonical form and not an alias{near}")
            print(f"\nverdict: {'hit' if hit else 'miss'}")
        if log:
            _log(bundle, "drill", text, against, land, drift,
                 "hit" if hit else "miss")
        return 0 if hit else 1

    verdict = "lands" if not drift else "drifts"
    if as_json:
        print(json.dumps({"verdict": verdict, **result}, indent=2))
    else:
        print(f"{key} — {len(land) + len(drift)} content phrases · "
              f"{len(land)} land · {len(drift)} drift\n")
        if land:
            print("  land")
            width = max(len(h["text"]) for h in land)
            for hit in land:
                entry_id = hit["id"]
                anchor = _first_anchor(bundle, entry_id)
                print(f"    {hit['text']:<{width}}  {entry_id}"
                      + (f"  {anchor}" if anchor else "")
                      + (f"  ({hit['why']})" if hit["why"] != "canonical form"
                         else ""))
        if drift:
            print("\n  drift  (each one is a place the agent must guess)")
            width = max(len(d["text"]) for d in drift)
            for miss in drift:
                if miss["nearest"]:
                    near = ", ".join(
                        f"{n['id']} ({n['score']})" for n in miss["nearest"])
                    print(f"    {miss['text']:<{width}}  nearest {near}")
                else:
                    print(f"    {miss['text']:<{width}}  no entry in this "
                          f"register")
        covering = _covering_phrasings(bundle, land)
        if covering:
            print("\n  phrasings that already name this")
            for entry_id in covering:
                for line in _entry_lines(bundle, entry_id, "    "):
                    print(line)
        print(f"\nverdict: {verdict}"
              + (f" ({len(drift)} ungrounded)" if drift else ""))
        if drift:
            print(f"rewrite using the entries above, then re-run "
                  f"{cmd('grade …')} — it must exit 0.")
    if log:
        _log(bundle, "instruction", text, against, land, drift, verdict)
    return 0 if verdict == "lands" else 1


def _first_anchor(bundle: RegisterBundle, entry_id: str) -> str:
    kind, _, slug = entry_id.partition(":")
    source = {"term": "lexicon", "phrase": "phrasebook"}.get(kind)
    if not source:
        return ""
    data = bundle.data[source].get(slug) or {}
    anchors = data.get("anchors") or []
    if not anchors:
        return ""
    return f"{anchors[0]['chapter']} @ {anchors[0]['curated_against']}"


def _log(bundle: RegisterBundle, kind: str, text: str, against: str | None,
         land: list[dict], drift: list[dict], verdict: str) -> None:
    """Append-only, under work/ — scratch, not substrate. Transfer happens
    "after enough calibration", and enough is a quantity over time; a coach
    with no memory can do lookup but not calibration."""
    path = calibration_log(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "register": f"{bundle.corpus.name}/{bundle.corpus.register}",
        "kind": kind,
        "against": against,
        "text": text,
        "hits": [h["id"] for h in land],
        "misses": [d["text"] for d in drift],
        "verdict": verdict,
    }
    with path.open("a") as handle:
        handle.write(json.dumps(record) + "\n")
