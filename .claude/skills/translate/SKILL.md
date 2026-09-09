---
name: translate
description: >
  Author or repair a register's extracted linguistic structure (lexicon,
  phrasebook, concept relations) for mounted chapters via the API-native
  authoring stage (`tools.lingua author` — Batch API + structured outputs),
  with the orchestrator applying results as the single writer and a human
  gating redefinitions and commits. Args: chapter ids (e.g. "foundations/03
  mcp/02"), a group name, a register, or "all"; with no args, targets every
  chapter with any tracked state not ok. Subagent authoring remains only as
  a fallback for one-off chapters without API credentials.
---

> **Superseded.** This skill now lives in the `ch` plugin as `/ch:translate` (`plugins/ch/skills/translate/SKILL.md`). That copy is the maintained one; prefer it. Delete `.claude/skills/` once the plugin resolves.

You are the orchestrator of the extraction loop. Authoring runs through the
API-native stage (`uv run python -m tools.lingua author`), which is cheap
(Sonnet-class model, Batch API at 50% pricing, one shared prompt-cache
prefix per run) and deterministic about conflicts. Every repo write goes
through the CLI's validate/apply path — you never hand-edit
`corpora/*/v*/data/*.yaml`.

## Target selection

Run `uv run python -m tools.lingua status --json` from the repo root.
Chapter ids are `<corpus>/<vN>/<group>/<NN>`; shorthands
`<corpus>/<group>/<NN>` and bare `<group>/<NN>` resolve when unambiguous.

- explicit ids in args → those chapters;
- `<corpus>/<vN>` → that register's chapters with any tracked state ≠ ok;
- a bare corpus name → its only register (several → ask via AskUserQuestion);
- a group name → that group's not-ok chapters (ambiguous → ask);
- `all` → every register, **one authoring run per register** (the stage
  enforces one register per run);
- no args → every chapter where any tracked dimension state is not `ok`.

Only tracked modes are in play (the `states` object lists them). Report
recorded-but-unimplemented modes as out of scope.

## Main loop (per register)

1. **Submit.** `uv run python -m tools.lingua author <target> [--sync]` —
   use `--sync` for ≤3 chapters (immediate, full price), the default Batch
   API otherwise (usually <1 h, half price). The stage authors every not-ok
   dimension per chapter in ONE pass; there is no lexicon-first round —
   apply ordering handles the dependency.
2. **Collect.** `uv run python -m tools.lingua author --collect --wait`.
   Report the printed usage line (tokens in/cached/out) to the user —
   observability of spend is part of the job. FAILED rows (refusals,
   truncations, API errors) → resubmit just those ids as a new
   `author <ids> --sync` run after the current one is applied.
3. **Apply (single writer).** `uv run python -m tools.lingua author --apply`.
   The stage validates each payload with the full `set` machinery (verbatim
   quote grounding, caps, slug existence) and applies serially — lexicon for
   all chapters first, then phrasebook, then relations. Undeclared
   define-conflicts are auto-demoted to mentions (anchors kept) and listed —
   no revision round needed. Read the output:
   - `REJECTED <chapter> <dim>` rows → step 4.
   - `HELD for the redefinition gate` rows → step 5.
4. **Retry rejects.** First run the /verify skill's triage on the
   register — it classifies each rejection (cascade vs. genuine vs.
   mechanical) and yields the retry id set with correct ordering; a
   cascade dependent retried without its bounced definer just bounces
   again. Then `uv run python -m tools.lingua author --retry <id...>`
   re-authors the rejected chapters synchronously with their stored
   violations and previous payloads attached; then `author --apply`
   again. **At most 2 retries per chapter**; after that, park it on a
   "needs human review" list and move on.
5. **Human gate: redefinitions.** For each held chapter the stage prints
   the declared redefinitions (slug, current owner, the author's reason)
   and writes the chapter's payloads to `work/authoring/gated/`, with the
   exact `set` commands. Show the current entry vs the proposed one and get
   approval:
   - approved → run the printed commands (`set lexicon … --redefine`, then
     the plain `set` commands for the other dimensions);
   - rejected → edit the gated **payload file** (never `data/*.yaml`) to
     demote that entry to `define: false` (slug + anchors only — a
     mechanical transform, no content authored), then run the printed
     commands without `--redefine`.
   Running unattended: do NOT apply redefinitions; leave them held and list
   every one prominently in the final report.
6. **Validate (sampled).** Launch `lingua-validator` subagents on a sample:
   one chapter per group, plus every chapter that needed a retry or a
   redefinition. A `fail` verdict → one `author --retry` with the
   validator's issues pasted into the chapter's `failures.json` entry (or
   quoted in the retry prompt), re-apply, re-validate. Same 2-round cap.
   Full-sweep validation only if the user asks — it costs more than the
   authoring did.

## Finishing (never skip)

1. Full `uv run python -m tools.lingua` build, then
   `uv run python -m tools.lingua check --strict` (strict exit 1 is
   expected while untargeted chapters remain unauthored — judge success on
   the chapters you targeted).
2. Report a table: chapter | lexicon | phrasebook | concept-relations |
   retries | auto-demotions | redefinitions (applied/held) | parked reason.
   Include the collected usage totals.
3. **Human gate on commits:** `corpora/` is gitignored — extraction output
   is never committed. If anything under the REPO changed, show
   `git diff --stat` and ask; never commit or push without instruction.

## Fallback: subagent authoring

When the API stage is unusable (no credentials for the `anthropic` SDK) or
for a single chapter during an interactive session, fall back to the
`lingua-author` subagent (`.claude/agents/lingua-author.md`): one chapter
per agent, result JSON to your scratchpad, apply via
`uv run python -m tools.lingua set <dim> <id> --from <file>` yourself —
lexicon before phrasebook/relations in that flow, since payloads apply one
dimension at a time. Prefer the API stage for anything larger than a couple
of chapters; it is an order of magnitude cheaper.

## Guardrails (restate to yourself before starting)

- Never modify anything under `corpora/*/source/` — corpus material is
  read-only.
- Never hand-edit `corpora/*/v*/data/*.yaml`: content flows only
  author-result → validate → apply/`set`. Editing a *payload file* to
  demote a rejected redefinition is allowed — that is input, and the
  transform is mechanical.
- One `--apply` at a time; it is the single writer.
- `accept-drift` re-blesses content as-is; prefer re-authoring unless a
  human reviewed the stale content.
