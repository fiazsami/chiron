# Lexicon — what things are called here

## Theory

The lexicon is the substrate's foundation. Prompting an agent about a corpus
is mostly the act of naming: the file you mean, the concept you want changed,
the command you expect it to run. When the learner's name for a thing matches
the corpus's name, the agent resolves it in one hop; when it doesn't, the
agent interpolates — and interpolation is where instructions go wrong.

A lexicon entry captures one thing the corpus names: the canonical surface
form ("context window", `chromadb.Client()`, `translation.yaml`), what kind
of name it is, a definition in the corpus's own words, and verbatim anchors
proving the corpus really says this. The definition is deliberately short —
the lexicon teaches *naming*, not the material itself.

Terms are corpus-scoped: one entry per concept, however many chapters touch
it. The chapter that establishes a term owns its definition (`defined_in`);
other chapters add mention anchors. This mirrors how vocabulary actually
lives in a repository — defined once, used everywhere.

## Extraction procedure

Work only from the extract bundle. If the chapter doesn't say it, it is not
in the lexicon.

1. Read the `## Lexicon slug index` first. Every existing slug is a term you
   must **reuse**, never re-mint: mention it (`define: false`) unless this
   chapter is genuinely its defining chapter.
2. Sweep the chapter content for names the corpus commits to:
   - domain ideas it defines or leans on (`kind: concept`),
   - proper names of components, services, layers (`kind: name`),
   - code identifiers — classes, functions, config keys (`kind: identifier`),
   - commands the reader is told to run (`kind: command`),
   - load-bearing files and paths (`kind: file`),
   - fixed values, defaults, magic constants (`kind: value`).
3. Skip generic vocabulary the corpus doesn't own ("function", "server",
   "test") unless the corpus gives it a specific local meaning.
4. For each new term, choose the canonical surface form the corpus itself
   uses most; record competing spellings as `aliases`.
5. Write the definition from the chapter's own words — compressed, not
   invented. Keep concrete details that make the term usable in a prompt
   (signatures, defaults, file locations).
6. Anchor every entry with 1–8 verbatim quotes copied exactly from the
   bundle. For code chapters, include the anchor's `path`. The `set` command
   rejects quotes it cannot find — do not paraphrase inside a quote.
7. Only set `define: true` for terms this chapter establishes. If the slug
   index shows the term defined by another chapter and you believe this
   chapter's definition should win, keep `define: true` and say why — the
   orchestrator gates the redefinition with a human.

## Schema and caps

Payload for `uv run python -m tools.lingua set lexicon <id> --from payload.json`:

```json
{"terms": [
  {"slug": "context-window",
   "define": true,
   "term": "context window",
   "kind": "concept",
   "definition": "The token budget holding everything the model can see in one call.",
   "aliases": ["ctx window"],
   "anchors": [
     {"chapter": "foundations/01",
      "path": "foundations/01-context.md",
      "quote": "The context window holds everything the model can see in one call"}
   ]},
  {"slug": "retrieval",
   "define": false,
   "anchors": [{"chapter": "foundations/01", "quote": "before retrieval is introduced"}]}
]}
```

- ≤ 40 terms per payload; the whole lexicon caps at 500 terms.
- `slug`: `[a-z0-9][a-z0-9-]*`, unique within the payload.
- `define` is required. `true` upserts the full entry; `false` is
  mention-only — just `slug` + `anchors`, the term must already exist.
- With `define: true`: `term` ≤ 80 chars; `kind` ∈ concept | name |
  identifier | command | file | value; `definition` ≤ 400 chars;
  `aliases` optional, ≤ 6, each ≤ 80 chars.
- `anchors`: 1–8 per entry. Each has `chapter` (must equal the target
  chapter), `quote` (8–240 chars, found verbatim in the chapter's files
  after whitespace normalization), and `path` (source-relative; required
  for code chapters, must be one of the chapter's files).
- Redefining a term whose `defined_in` is another chapter is rejected
  unless the orchestrator passes `--redefine`.
- A `set` for chapter C first drops all of C's existing anchors, then
  applies the payload; entries left with no anchors are removed.

## Quality bar

Errors (any one fails the chapter):

- **contradicted** — the definition says something the chapter's text does not.
- **not-in-chapter** — `define: true` for a term the chapter never establishes.
- **wrong-canonical-form** — the corpus consistently writes X; the entry
  canonicalizes Y (the corpus's spelling wins, even when it is unusual).
- **duplicate-sense** — two slugs for one concept, or one slug stretched over
  two distinct concepts.

Warnings:

- **vague** — a definition carrying no corpus-specific information (it could
  describe any repository).

## Worked example

For a fictional two-file repo where `pipeline.py` contains
`# stages run in declaration order; a stage returning None halts the run`:

```json
{"terms": [
  {"slug": "stage", "define": true, "term": "stage", "kind": "concept",
   "definition": "One step of the pipeline; stages run in declaration order and a stage returning None halts the run.",
   "anchors": [{"chapter": "core/01", "path": "pipeline.py",
                "quote": "stages run in declaration order; a stage returning None halts the run"}]}
]}
```
