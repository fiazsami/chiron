---
name: translate
description: >
  Author or repair a register's extracted linguistic structure (lexicon,
  phrasebook, concept relations) for mounted chapters using author/validator
  subagents. Args: chapter ids (e.g. "foundations/03 mcp/02"), a group name,
  or "all"; with no args, targets every chapter with any tracked state not
  ok. The loop is orchestrated: parallel authors draft payloads, an
  independent validator judges the stored entries, the orchestrator is the
  single writer via `set`, and a human gates redefinitions and commits.
---

You are the orchestrator (and the single writer) of the extraction loop.
All repo writes happen in the main loop — subagents never touch the repo.

## Target selection

Run `uv run python -m tools.lingua status --json` from the repo root (the
directory holding `tools/` and `corpora/`). Chapter ids are
`<corpus>/<vN>/<group>/<NN>` (e.g. `fewshot-works-academy/v1/foundations/03`);
two shorthands resolve when unambiguous: `<corpus>/<group>/<NN>` (corpus has
one register) and the bare `<group>/<NN>` (exactly one mounted register
matches). Then:

- explicit ids in args → those chapters (validate ids against the status
  list, resolving shorthand ids);
- `<corpus>/<vN>` (e.g. `fewshot-works-academy/v1`) → all chapters in that
  register;
- a bare corpus name → its only register; if the corpus has several, ask
  which via AskUserQuestion rather than guessing;
- a group name (e.g. `foundations`, `mcp`) or `<corpus>/<vN>/<group>` → all
  chapters in that group (a bare group must resolve within a single
  register; ambiguity → ask);
- `all` → every chapter of every register;
- no args → every chapter where any tracked dimension state is not `ok`.

Only the register's tracked modes are in play: the `states` object in the
status JSON lists them per chapter. Mention the register's modes in the
final report, and list recorded-but-unimplemented modes as out of scope —
never attempt to author content for a mode with no machinery.

## Translation requirements

Each register's `translation.yaml` states its modes and free-text
requirements; the extract bundle carries them in a "Translation
requirements" section, so authors and validators see them without extra
plumbing.

## Subagent types

Prefer `subagent_type: "lingua-author"` / `"lingua-validator"` (defined in
`.claude/agents/`). If those types are not registered in this session (the
Agent tool rejects them), fall back to `general-purpose` subagents whose
prompt begins: "Read .claude/agents/lingua-author.md (resp.
lingua-validator.md) at the repo root and follow it exactly," followed by the
same task inputs.

## Main loop — batches of at most 4 chapters

**Dimension ordering per chapter: lexicon first.** Phrasebook and
concept-relations payloads reference lexicon slugs, so `set` rejects them
until the slugs exist — author them only once that chapter's lexicon is ok.
In practice each batch runs two author rounds:

- **Round A — lexicon.** One author subagent per chapter, dimensions:
  `lexicon`. Apply all round-A results before starting round B.
- **Round B — phrasebook and concept-relations** (those of the two the
  register tracks), against the now-updated lexicon.

For each round:

1. **Author (parallel).** One author subagent per chapter. Give each: the
   chapter id, the target dimension(s) for this round, a unique absolute
   output path in YOUR scratchpad directory, and — on revision rounds — the
   validator issues and/or `set` violations to fix.
2. **Human gate: redefinitions (before applying).** A non-empty
   `redefinitions` list in a result JSON means the author wants
   `define: true` on slugs currently defined by another chapter — a plain
   `set` will reject exactly that with a `requires --redefine` violation.
   For each declared redefinition: show the current lexicon entry, the
   proposed one, and the author's reason, and get approval. Approved → that
   payload's `set` gets `--redefine`; rejected → bounce the payload to the
   author to demote the entry to `define: false` (or drop it), which counts
   as a revision round. When running unattended you may apply with
   `--redefine`, but MUST list every redefinition prominently in the final
   report. Never pass `--redefine` for anything the author didn't declare —
   an undeclared `requires --redefine` violation is an author error and
   bounces like any other.
3. **Apply (serial, orchestrator only).** For each result JSON, in order,
   and for each non-null dimension in it: write the payload object to a temp
   file, then run
   `uv run python -m tools.lingua set <dimension> <id> --from <file>`
   (plus `--redefine` only when step 2 approved that payload's
   redefinitions). Exit 2 lists every violation — send the printed list back
   to that chapter's author (counts as a revision round).
4. **Validate (parallel).** After round B (or after round A when lexicon is
   the only tracked mode), one validator subagent per chapter against the
   updated stored state; parse the verdict JSON from the end of each final
   message.
5. **Revise.** `verdict: fail` → relaunch that chapter's author with the
   issues attached (lexicon issues go back to a round-A style task, the rest
   to round B); then re-apply and re-validate. **At most 2 revision rounds
   per chapter**; after that, park the chapter on a "needs human review"
   list and move on. If the author rebuts an issue with a supporting quote
   from the bundle, you arbitrate: check the quote yourself and drop or
   uphold the issue.

## Finishing (never skip)

1. Full `uv run python -m tools.lingua` build, then
   `uv run python -m tools.lingua check --strict` for the report (strict
   exit 1 is expected while other chapters remain unauthored — judge success
   on the chapters you targeted).
2. Report a table: chapter | lexicon | phrasebook | concept-relations |
   rounds used | redefinitions applied | parked reason. Note out-of-scope
   recorded modes.
3. **Human-in-the-loop gate:** extraction output lives under `corpora/`,
   which is gitignored — it is never committed. If anything under the REPO
   itself changed, show `git diff --stat` and ask before committing; never
   commit or push without an explicit instruction.

## Guardrails (restate to yourself before starting)

- Never modify anything under `corpora/*/source/` — corpus material is
  read-only.
- Subagents are repo-read-only; every write goes through you, serially —
  one `set` at a time.
- Never hand-edit `corpora/*/v*/data/*.yaml`: content flows only
  author → result JSON → `set`. If a chapter needs different entries,
  that's a new author round, not an orchestrator edit.
- `accept-drift` re-blesses content as-is; prefer re-authoring unless a
  human reviewed the stale content.
