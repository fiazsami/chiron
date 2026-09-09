# The chiron methodology

## Operating theory

Every repository has a working language. Its authors chose names for things —
types, commands, config keys, domain ideas — and settled into fixed ways of
combining them. That language is not decoration: it is the repository's own
index into itself. An instruction phrased in the corpus's terms lands, because
the words in the instruction are the words in the code and the docs; an
instruction phrased in generic terms drifts, because the agent must guess the
mapping and every guess is a place to be wrong.

chiron extracts that working language as data — the **linguistic substrate**
of the corpus — so a human can calibrate their own language against it. The
substrate is not a summary. It answers three questions a summary never asks:

1. **What is this called here?** — the *lexicon*: terms, names, and
   identifiers with grounded definitions.
2. **How do I say it when instructing an agent?** — the *phrasebook*:
   canonical phrasings and instruction templates.
3. **How do the names relate?** — the *concept relations*: typed links
   between lexicon entries.

Every entry is anchored to a verbatim quote from the corpus, pinned to the
content hash the quote was authored against. Grounding is enforced by the
tooling, not by good intentions: `set` rejects any quote it cannot find in
the chapter, and a chapter that changes marks exactly its own anchors stale.

The learner works the substrate two ways: by **browsing the evidence** in the
web viewer, and by **practising the language in Claude Code** — `/ch:calibrate`
is a coach that answers "what is X called here", rewrites the learner's
instructions into the corpus's own phrasing, and quizzes articulation. It
grades every answer against the substrate rather than against its own
opinion: `./ch grade` reports which parts of an instruction name something
this corpus names and which parts an agent would have to guess at, and its
verdict is an exit code, for the same reason `set` rejects a quote it cannot
find. Practice lives where instructions are actually typed. The goal is
transfer: after enough calibration, the learner prompts any agent about this
corpus in its own terms without looking anything up.

One addressable unit of the substrate — one term, one phrasing, one relation
edge — is an **entry**. Entries are what `ask` returns, what `grade` matches
against, and what the viewer's lookup renders; they are never addressed by a
URL of their own.

## The modularity contract

A **dimension** of the substrate is:

- one mode slug (used in `translation.yaml` `modes:` and everywhere else),
- one plan document here — `methodology/<slug>.md`,
- one implementation module — `tools/lingua/dimensions/<module>.py`,
  registered in `tools/lingua/dimensions/__init__.py`.

The three names are the same string. A methodology document without an
implementation is a **recorded** mode: `/ch:mount` stores it, the tooling
surfaces it, nothing renders it yet. That is how a new dimension enters the
system — write the plan first, ship the machinery when it earns it.

Each dimension document follows a fixed skeleton:

| Section | Audience |
|---|---|
| `## Theory` | the human — why this dimension improves prompting |
| `## Extraction procedure` | the authoring agent — imperative steps |
| `## Schema and caps` | both — mirrors the validator exactly |
| `## Quality bar` | the validating agent — what to reject |
| `## Worked example` | both — one micro-example payload |

Sections 2–4 are embedded verbatim into every chapter's extract bundle
(`./ch extract <id>`), so the plan steers the
authoring agents directly — the methodology is executed, not merely cited.
The code (`validate_payload` in each dimension module) is the source of truth
for the schema; when a validator changes, its `## Schema and caps` section
changes in the same commit.

## Shipped dimensions

- [`lexicon`](lexicon.md) — terms, names, identifiers with grounded
  definitions. Authored first: the other dimensions reference its slugs.
- [`phrasebook`](phrasebook.md) — canonical phrasings for instructing an
  agent about this corpus.
- [`concept-relations`](concept-relations.md) — typed links between lexicon
  entries.
