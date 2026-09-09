# Concept relations — how the names relate

## Theory

Names alone are a bag of words; the structure between them is what lets a
learner reason in the corpus's terms. "Retrieval *feeds* the context window",
"the adapter *implements* the scan contract", "a register *is part of* a
corpus" — typed links like these are the difference between knowing
vocabulary and speaking the language. In a prompt, relations are what make
multi-step instructions coherent: you can only say "wire X into Y" correctly
if you know X feeds Y and not the reverse.

A relation is one typed edge between two lexicon entries, with a one-line
gloss and anchors proving the corpus asserts the link. The type set is closed
so the viewer and the learning agent can rely on edge semantics; extending it
is a deliberate change (one line of code plus this document), not a per-entry
choice.

## Extraction procedure

Work only from the extract bundle. An edge exists because the chapter says
so, not because it is plausible.

1. Read the `## Lexicon slug index`; both endpoints of every edge must name
   existing slugs. Missing endpoint → the lexicon round missed a term; flag
   it rather than inventing the slug.
2. Sweep the chapter for asserted connections between lexicon terms —
   sentences and code where one named thing contains, produces, configures,
   or precedes another.
3. Pick the type from the closed set:
   - `is-a` — kind/instance ("a register is a retelling of the corpus"),
   - `part-of` — containment ("a chapter is part of a group"),
   - `uses` — dependency without data flow ("the adapter uses gittree"),
   - `feeds` — output of one becomes input of the other,
   - `configures` — one thing sets the other's behavior,
   - `contrasts-with` — the corpus explicitly distinguishes the two,
   - `implements` — a concrete thing realizes a contract/idea,
   - `precedes` — required ordering.
4. Direction matters: `from` is the actor/source, `to` the target. Write the
   gloss so it reads left to right ("retrieved chunks are packed into the
   window").
5. Anchor each edge with 1–8 verbatim quotes; the quote should carry the
   assertion, not just mention both terms. Same grounding rules as the
   lexicon; `path` required for code chapters.
6. Skip edges that restate another edge with a weaker type — one precise edge
   beats two loose ones.

## Schema and caps

Payload for `./ch set concept-relations <id> --from payload.json`:

```json
{"edges": [
  {"from": "retrieval",
   "to": "context-window",
   "type": "feeds",
   "gloss": "retrieved chunks are packed into the window before the call",
   "anchors": [
     {"chapter": "rag/01", "quote": "Retrieved documents are appended to the prompt before the call"}
   ]}
]}
```

- ≤ 30 edges per payload.
- `from` / `to`: existing lexicon slugs, distinct from each other — lexicon
  before relations.
- `type` ∈ is-a | part-of | uses | feeds | configures | contrasts-with |
  implements | precedes.
- `gloss` ≤ 200 chars, single line, required.
- `anchors`: 1–8, same rules as the lexicon (target chapter only, verbatim
  quote 8–240 chars, `path` required for code chapters).
- Edges are keyed by `(from, type, to)`: a duplicate within a payload is
  rejected; a second chapter anchoring the same edge merges its anchors in
  (gloss is last-writer-wins).
- A `set` for chapter C drops C's anchors first; edges left with no anchors
  are removed. An edge whose endpoint later vanishes from the lexicon marks
  its anchoring chapters stale — a dangling edge is drift even when hashes
  match.

## Quality bar

Errors:

- **wrong-type** — the chapter asserts a different relationship than the
  type claims (or the edge points the wrong way).
- **unsupported-edge** — the anchors mention both terms but never assert the
  link between them.

Warnings:

- **redundant-edge** — restates another edge without adding information.

## Worked example

For the fictional pipeline repo where the README says
`the runner walks the stages and hands each one the previous stage's output`:

```json
{"edges": [
  {"from": "stage", "to": "runner", "type": "feeds",
   "gloss": "each stage's output is handed to the next by the runner",
   "anchors": [{"chapter": "core/01", "path": "README.md",
                "quote": "hands each one the previous stage's output"}]}
]}
```
