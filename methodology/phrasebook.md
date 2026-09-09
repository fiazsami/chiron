# Phrasebook — how to say it when instructing an agent

## Theory

Knowing the names is necessary but not sufficient; the corpus also has fixed
ways of *combining* them. "Register a tool on the MCP server", "mount a
corpus", "pin the anchor to the content hash" — these collocations carry the
mechanics of the system inside their grammar: the verb tells the agent which
operation, the preposition tells it which relationship. A learner who
commands the phrasing writes instructions that read like the corpus wrote
them — and the agent executes them the way the corpus intends.

A phrasebook entry captures one canonical phrasing: the collocation itself,
the intent it serves (when you'd reach for it), an optional instruction
template with `{slots}` the learner fills in, and the lexicon terms it leans
on. Phrases reference lexicon slugs, so a chapter's lexicon is authored
before its phrasebook.

## Extraction procedure

Work only from the extract bundle. Extract phrasings the corpus uses, not
phrasings you would use.

1. Read the `## Lexicon slug index`; every phrase's `terms` list must name
   existing slugs. If a phrase needs a term that isn't there, the lexicon
   round missed it — flag it rather than inventing the slug.
2. Sweep the chapter for verb–object patterns the corpus repeats or commits
   to: how it says to create, register, wire, run, or check its own things.
   The strongest candidates are phrasings a reader must get right to operate
   the system ("re-pin `curated_against`", "delegate to the markdown
   adapter").
3. Write `phrase` as the collocation in the corpus's own voice, `intent` as
   the one-line situation it serves.
4. Add a `template` only when the phrasing naturally extends into a reusable
   instruction; mark the variable parts as `{slots}`. The template should be
   something the learner could paste into a prompt after filling the slots.
5. Anchor each phrase with 1–8 verbatim quotes showing the corpus using (or
   defining) the phrasing. Same grounding rules as the lexicon: exact copy,
   `path` required for code chapters.
6. Prefer few, load-bearing phrases over many incidental ones — the payload
   cap is deliberately small.

## Schema and caps

Payload for `./ch set phrasebook <id> --from payload.json`:

```json
{"phrases": [
  {"slug": "append-retrieved-docs",
   "phrase": "append the retrieved documents to the prompt",
   "intent": "describe the retrieval hand-off",
   "template": "Retrieve with {query}, then append the retrieved documents to the prompt before the call.",
   "terms": ["retrieval", "context-window"],
   "anchors": [
     {"chapter": "rag/01", "quote": "Retrieved documents are appended to the prompt"}
   ]}
]}
```

- 1–15 phrases per payload.
- `slug`: `[a-z0-9][a-z0-9-]*`, unique within the payload.
- `phrase` ≤ 160 chars, single line. `intent` ≤ 160 chars, single line.
- `template` optional, ≤ 300 chars, may be multi-line, `{slots}` allowed.
- `terms`: non-empty list of lexicon slugs that already exist — lexicon
  before phrasebook.
- `anchors`: 1–8, same rules as the lexicon (target chapter only, verbatim
  quote 8–240 chars, `path` required for code chapters).
- A `set` for chapter C drops C's anchors first; phrase content is
  last-writer-wins; entries left with no anchors are removed.

## Quality bar

Errors:

- **unidiomatic** — a phrasing the corpus never uses; the extractor's own
  words dressed up as the corpus's.
- **wrong-term-link** — `terms` lists slugs the phrase doesn't actually lean
  on, or misses the ones it does.
- **template-contradicts-source** — the template instructs something the
  chapter says to do differently.

Warnings:

- **low-utility** — a phrasing nobody would need in an instruction (incidental
  prose rather than an operating collocation).

## Worked example

For the fictional pipeline repo whose README says
`add a stage by decorating a function with @stage; order follows declaration`:

```json
{"phrases": [
  {"slug": "add-a-stage", "phrase": "add a stage by decorating a function with @stage",
   "intent": "extend the pipeline",
   "template": "Add a stage named {name} by decorating {function} with @stage; keep declaration order in mind.",
   "terms": ["stage"],
   "anchors": [{"chapter": "core/01", "path": "README.md",
                "quote": "add a stage by decorating a function with @stage"}]}
]}
```
