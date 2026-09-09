---
name: verify
description: >
  Read-only: where a register stands and what to do next. Reports the state
  of every tracked dimension, the health of any open authoring run, and — when
  an apply bounced — a triage of every rejection classified as cascade,
  genuine grounding failure, or mechanical violation, with the correctly
  ordered retry plan. Never writes; /ch:translate owns every write. Args: a
  target expression; with no args, every mounted register. Use to orient, to
  audit an authoring run, or whenever an apply printed REJECTED rows.
---

Read `../GRAMMAR.md` first. You are strictly read-only: no `--retry`, no
`--apply`, no `set`, no `accept-drift`, no edits to payloads or `data/*.yaml`.
You produce a plan; `/ch:translate` executes it.

## Invariants

- Write nothing. Not a payload, not a data file, not a work file.
- Never trust memory of the source: chapter material comes from
  `./ch extract <id>` or the files it lists.
- Quote comparisons use the grounding check's own equivalence — collapse all
  whitespace runs to single spaces before searching
  (`tools/lingua/dimensions/base.py`, `normalize`).

## Target

`./ch resolve $ARGS`. No args → every mounted register.

## Loop

1. **Orient.** `./ch where`. For a register with no open run and nothing
   stale, that line plus a one-paragraph reading of `./ch status` is the whole
   job — say so and stop.
2. **Run health.** `./ch author --status <register>` for any register with an
   open run. It reports, deterministically: per-chapter run state and attempt
   count; chapters that never produced a result (a collect-level failure — the
   fix is a fresh run, not a retry); a `failures.json` older than the newest
   result (a previous round — say so rather than re-triaging it); result files
   left over from an earlier run; and cascade classification with the ordered
   retry set. Do not re-derive any of that by reading files yourself.
3. **Judge what is left.** `--status` resolves cascades. What remains needs a
   reader:
   - **`'<slug>' is not in the lexicon`, no bounced definer.** Does the term
     appear in this chapter's material? Then the author chose mention where no
     definition exists anywhere — the retry should consider `define: true`
     here. Otherwise it is an invented reference.
   - **`quote not found in the chapter's files`.** Grep a distinctive
     substring of the normalized quote. Near match in this chapter →
     paraphrase; retry-with-reasons usually fixes it. Verbatim match in a
     *different* chapter → the author quoted the wrong chapter. No match
     anywhere → hallucinated.
   - **Mechanical violations** — slug pattern, quote over 240 chars, missing
     or wrong `path` on a code chapter. The API schema cannot express these,
     so they surface only at apply. Content is usually salvageable.
4. **Read the applied state.** A chapter that is neither rejected nor held but
   still not ok usually returned an empty collection — a deliberate skip, since
   the schema cannot express minItems. Confirm from its result file and report
   it as "author found nothing to contribute", not as a failure.

## Gates

None. This skill asks the user nothing; it hands them decisions in the report.

## Report

Per `GRAMMAR.md`, then:

1. A table: chapter | dimension | problem | classification | action.
2. The retry command(s) exactly as `./ch author --status` printed them —
   every bounced definer alongside its dependents in one set. Chapters at the
   two-retry cap go on a "needs human review" list instead.
3. Held redefinitions, verbatim, for `/ch:translate`'s Gate R.
4. Anything needing a human decision, **stated as a decision, not a task** —
   the choice, both options, and what each costs.

Do not execute the plan. Hand it off.
