---
name: verify
description: >
  Post-apply triage for an authoring run. Reads a register's
  work/authoring state (run.json, results/, failures.json, gated/) plus
  the applied data/*.yaml, classifies every rejection — cascade failure,
  genuine grounding failure, or mechanical violation — and emits a retry
  plan with correct ordering. Strictly read-only: it recommends the exact
  `author --retry` command but never writes; /translate remains the
  single writer. Args: a register (e.g. "12-factor-agents/v1"); with no
  args, the register whose work/authoring/run.json exists. Run after
  /translate's apply step, or whenever an apply printed REJECTED rows.
---

> **Superseded.** This skill now lives in the `ch` plugin as `/ch:verify` (`plugins/ch/skills/verify/SKILL.md`). That copy is the maintained one; prefer it. Delete `.claude/skills/` once the plugin resolves.

You are the post-apply auditor. An `author --apply` run has finished and
some payloads may have bounced. Your job is diagnosis, not repair: every
rejection gets a classification and a fix path, and the output is a plan
the user (or a /translate run) executes. You never modify anything —
no `--retry`, no `--apply`, no `set`, no edits to payloads or
`data/*.yaml`.

## Locate the run

Resolve the register from args, or find the one with
`corpora/<corpus>/<vN>/work/authoring/run.json` (several → ask via
AskUserQuestion). In that directory:

- `run.json` — batch id, model, and the planned chapters with their
  modes. Result files in `results/` are named by register-local id with
  `/` replaced by `--` (e.g. `factors--03.json`).
- `failures.json` — rejected payloads: `{local_id: {dim: [problems]}}`.
  Absent or empty after a clean apply.
- `gated/` — payloads held for the redefinition gate, if any.

## Health checks (before triage)

1. **Coverage.** Every chapter in `run.json` has a file in `results/`.
   Missing files mean collect-level failures — report them; the fix is a
   fresh `author <ids> --sync` run, not a retry.
2. **Applied state.** `uv run python -m tools.lingua status --json` —
   for each planned chapter, tracked dimensions should now be `ok`
   except those in `failures.json` or `gated/`. A chapter that is
   neither rejected nor gated but still not ok usually returned an empty
   collection (a deliberate skip — the API schema cannot express
   minItems); confirm by reading its result file, and report it as
   "author found nothing to contribute", not as a failure.
3. **Stale state.** A `failures.json` older than the newest file in
   `results/` describes a previous round — say so rather than
   re-triaging it.

## Triage (per rejection)

Classify each problem line in `failures.json`. Quote comparisons use the
grounding check's equivalence: collapse all whitespace runs to single
spaces before searching (`tools/lingua/dimensions/base.py` `normalize`).
Chapter material comes from `uv run python -m tools.lingua extract <id>`
or the source files it lists — never trust memory of the source.

- **`'<slug>' is not in the lexicon` (mention-only bounce).** Check, in
  order:
  1. Does a sibling chapter's payload in `results/` (or `gated/`) define
     that slug (`define: true`)? If that chapter's lexicon was itself
     rejected or held, this is a **cascade failure** — the mention is
     fine; the definer bounced. Fix: retry/unblock the definer, and
     include this chapter in the same retry set (apply processes
     register order, so the definition lands first).
  2. Otherwise, does the term appear in this chapter's source material?
     Then the author chose mention where no definition exists anywhere —
     suggest a retry noting it may need `define: true` here.
  3. Otherwise it is a **genuine error** (invented reference) — retry
     with reasons.
- **`quote not found in the chapter's files`.** Search the chapter's
  own files for a near match of the normalized quote (grep a distinctive
  substring). Near match found → **paraphrase**; retry-with-reasons
  usually fixes it. Verbatim match in a *different* chapter's material →
  the author quoted the wrong chapter; genuine, needs re-authoring. No
  match anywhere → **hallucinated quote**; genuine.
- **Mechanical violations** — slug fails the pattern, quote over 240
  chars, missing/wrong `path` on a code chapter: the API schema can no
  longer express these constraints (structured outputs rejects
  pattern/length keywords), so they surface only at apply. Content is
  usually salvageable; retry-with-reasons fixes them.

## Report

End with, in this order:

1. A table: chapter | dim | problem | classification | action.
2. The exact retry command(s): one
   `uv run python -m tools.lingua author --retry <id...>` whose id set
   includes every bounced definer alongside its dependents (register
   order handles the rest), followed by `author --apply`. Chapters
   already at /translate's 2-retry cap go on a "needs human review"
   list instead.
3. Held redefinitions from `gated/`, verbatim, for the human gate.
4. Anything that needs a human decision, stated as a decision, not a
   task.

Do not execute the plan. Hand it off — to the user, or to a /translate
run that owns the write loop.
