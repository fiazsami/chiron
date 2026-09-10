---
name: translate
description: >
  Author or repair a register's linguistic substrate (lexicon, phrasebook,
  concept relations) for mounted chapters, via the API-native authoring stage
  (Batch API + structured outputs), applying every result through the CLI's
  validate path as the single writer. Args: any target expression — chapter
  ids, a group, a register, or "all"; with no args, every chapter with a
  tracked state not ok. Use when chapters are unauthored or drifted, or after
  /ch:verify hands over a retry plan.
---

Read `../GRAMMAR.md` first. You are the orchestrator of the authoring loop,
and the **single writer** of `data/*.yaml`.

## Invariants

- Never hand-edit `devenv/reference/*/v*/data/*.yaml`. Content flows author-result →
  validate → apply.
- Never hand-edit a payload under `work/authoring/`. Both branches of the
  redefinition gate are files the CLI writes and commands the CLI prints.
- One `--apply` at a time.
- `accept-drift` re-blesses content as-is; prefer re-authoring.
- The rest are in `AGENTS.md § Invariants`.

## Target

`./ch resolve $ARGS`. No args → every chapter with a tracked state not ok.
`all` runs **one authoring run per register** — the stage enforces one
register per run. Only tracked dimensions are in play; report recorded
modes as out of scope.

## Loop

Orient with `./ch where`, then per register:

1. **Submit.** `./ch author <target> [--sync]` — `--sync` for ≤3 chapters
   (immediate, full price), Batch API otherwise (usually <1h, half price).
   Every not-ok dimension is authored in one pass; apply ordering handles the
   lexicon-first dependency.
2. **Collect.** `./ch author --collect --wait`. Report the printed usage line
   — observability of spend is part of the job. `FAILED` rows are
   collect-level failures: re-submit exactly those ids as a fresh run, not a
   retry.
3. **Apply.** `./ch author --apply`. This is the write. Read the output:
   - `applied` rows, with any `(auto-demoted: …)` note — an undeclared
     define-conflict resolved in favour of the earlier chapter. No action.
   - `skipped … — lexicon rejected` — that chapter's other dimensions were
     cancelled because they reference its slugs. They come back with the
     lexicon.
   - `REJECTED` rows → step 4. `HELD` rows → Gate R.
4. **Triage and retry.** Run `./ch author --status` — it classifies cascades
   mechanically and prints the correctly-ordered retry set. For anything it
   leaves as a genuine failure, judge it yourself (or hand the register to
   `/ch:verify` for the full read-only workup): paraphrase vs. wrong chapter
   vs. hallucinated quote; invented reference vs. a definition missing
   everywhere. Then `./ch author --retry <ids>` and apply again.
   **Two retries per chapter.** After that, park it — record the reason in
   `run.json` via the parked field and list it in the report.
5. **Validate (sampled).** Launch `lingua-validator` on one chapter per
   group, plus every chapter that needed a retry or a redefinition. A `fail`
   verdict earns one more retry round inside the same cap. Full-sweep
   validation only if the user asks — it costs more than the authoring did.
6. **Build.** `./ch` — pages, manifest, and any chroma store refresh.
   Then `./ch check`.

## Gates

```
GATE R — redefinition
  what changes   which chapter owns the definition of a term slug
  the material   `./ch author --apply` prints both definitions with their
                 anchors. Show them as printed. If they are not on screen,
                 re-run --apply; do not summarize from memory and do not ask
                 until they are.
  branches       accept:  the `set … --redefine` command it printed
                 reject:  the `set … --from …demoted.json` command it printed
                          (mention-only, anchors kept — already written for you)
  reversibility  re-runnable — `set` re-applies the chapter's entries wholesale
  unattended     leave held; list every one prominently in the report
```

```
GATE C — commit
  what changes   the repo, never devenv/ (gitignored in full)
  the material   `git diff --stat`
  branches       commit with a message the user approves, or leave it
  reversibility  reversible before push
  unattended     do not commit; report the diff
```

## Report

Per `GRAMMAR.md`, with these columns after the chapter id:
`lexicon | phrasebook | concept-relations | retries | auto-demotions |
redefinitions (applied/held) | parked reason`, plus the collected usage
totals. `./ch author --status` supplies the retry and parked columns —
read them from it rather than from memory.

## Fallback

Without API credentials (`./ch author` exits 2 naming
`ANTHROPIC_API_KEY`), fall back to the `lingua-author` subagent: one chapter
per agent, result JSON to your scratchpad, applied by you with
`./ch set <dimension> <id> --from <file>` — lexicon before the others, since
that path applies one dimension at a time. Prefer the API stage for anything
larger than a couple of chapters; it is an order of magnitude cheaper.
