# The shared shape

Read this before any `/ch:` skill. It holds what all four have in common, so
no skill restates it and no two can drift apart.

`AGENTS.md` at the repo root is loaded into every session and is the single
home for the **target grammar**, the **vocabulary**, the **states**, the
**invariants**, and the **contracts**. Do not restate those here or in a
skill — reference them. If a rule seems to be missing, it belongs in
`AGENTS.md`, not in one skill's prose.

## The rhythm — five beats, same order, every skill

**Orient → Target → Loop → Gates → Report.**

1. **Orient.** Run `./ch where` first. Never begin work without saying where
   you are. If the state line already answers the user's question, say so and
   stop — that is a complete turn.
2. **Target.** Resolve with `./ch resolve $ARGS` and echo the expansion before
   acting. Never act on an unstated target. Each skill states only its own
   no-args default.
3. **Loop.** The only beat that differs between skills.
4. **Gates.** The only beat permitted to ask the user a question.
5. **Report.** Fixed shape, below.

A sixth `## Fallback` section exists only where a genuinely degraded path
does.

## The gate object

Every human decision states five fields, in this order. **A gate that cannot
show its material is a bug, not a gate** — if you cannot print both sides,
go get them before you ask.

```
GATE <name>
  what changes   one sentence, in the target's own ids
  the material   both sides, inline, verbatim — never a pointer to go read
  branches       each with its exact runnable command
  reversibility  reversible | re-runnable | append-only (permanent)
  unattended     what happens when nobody is there to answer
```

Every gate has an unattended default. Running unattended is not a licence to
guess: the default is almost always *stop and report*.

## The report shape

Three parts, always in this order:

1. **The state line** — `./ch where` for the register you touched,
   byte-identical. Do not paraphrase it.
2. **A table** — first column is always the **full chapter id**; dimension
   columns are named by slug (`lexicon | phrasebook | concept-relations`),
   never abbreviated. Skill-specific columns hang off the right.
3. **One next action** — runnable, and matching what the CLI would print for
   that state. If your recommendation disagrees with `./ch where`, one of you
   is wrong; find out which before reporting.

## Voice

Mirror the CLI's law (`tools/lingua/__main__.py` docstring). In particular:
every command you show a user is copy-pasteable in full, and every chapter
you name to a human is named by its full id.

## What is machine work, and what is yours

The CLI is deterministic and owns every write. You own targeting, gates, and
judgement. When a check can be a file read, it is the CLI's job — do not
re-derive with a model what `./ch author --status` already computed.
