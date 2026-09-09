---
name: update-notes
description: >
  Author or repair curated notes content (key facts + flow schematics) for
  mounted chapters using author/validator subagents. Args: chapter ids
  (e.g. "foundations/03 mcp/02"), a group name, or "all"; with no args,
  targets every chapter whose facts or schematic is not ok. The loop is
  orchestrated: parallel authors draft, an independent validator judges, the
  orchestrator is the single writer, and a human gates flow fixes and commits.
---

You are the orchestrator (and the single writer) of the notes-authoring loop.
All repo writes happen in the main loop — subagents never touch the repo.

## Target selection

Run `uv run python -m tools.notes --status --json` from the repo root (the
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
- no args → every chapter where `facts != "ok"` or `schematic != "ok"`.

## Translation requirements

Each register's `translation.yaml` states its modes and free-text
requirements; the `--extract` bundle carries them in a "Translation
requirements" section, so authors and validators see them without extra
plumbing. Mention the register's modes in the final report, and list
recorded-but-unrendered modes (e.g. `design-patterns`) as out of scope —
never attempt to author content for a mode with no renderer.

## Subagent types

Prefer `subagent_type: "notes-author"` / `"notes-validator"` (defined in
`.claude/agents/`). If those types are not registered in this session (the
Agent tool rejects them), fall back to `general-purpose` subagents whose prompt
begins: "Read .claude/agents/notes-author.md (resp. notes-validator.md) at the
repo root and follow it exactly," followed by the same task inputs.

## Main loop — batches of at most 4 chapters

For each batch:

1. **Author (parallel).** One author subagent per chapter. Give each: the
   chapter id, a unique absolute output path in YOUR scratchpad directory, and —
   on revision rounds — the validator issues and/or `--set-facts` violations to
   fix.
2. **Apply (serial, orchestrator only).** For each result JSON, in order:
   - Write the `facts` object to a temp file; run
     `uv run python -m tools.notes --set-facts <id> --from <file>`.
     Exit 2 → send the printed violations back to that chapter's author
     (counts as a revision round).
   - If `flow_fix.needed`: this is a **human-in-the-loop gate** — show the
     current entry, the proposed `entry_yaml`, and the author's reason, and get
     approval before applying (when running unattended, you may apply it but
     must list every applied flow fix prominently in the final report, and must
     not push without an explicit instruction). To apply: edit that chapter's
     entry in `corpora/<corpus>/<vN>/data/flows.yaml` yourself (keyed by the
     register-local `<group>/<NN>` id), preserving its existing
     `curated_against` line; run a plain build so `load_flows` schema-checks
     it; run `--accept-drift <id>` only if that entry was already stale.
3. **Validate (parallel).** One validator subagent per chapter; parse the
   verdict JSON from the end of each final message.
4. **Revise.** `verdict: fail` → relaunch that chapter's author with the
   issues attached; then re-apply and re-validate. **At most 2 revision rounds
   per chapter**; after that, park the chapter on a "needs human review" list
   and move on. If the author rebuts an issue with a supporting quote from the
   bundle, you arbitrate: check the quote yourself and drop or uphold the issue.

## Finishing (never skip)

1. Full `uv run python -m tools.notes` then `--strict` for the report
   (strict exit 1 is expected while other groups remain unauthored — judge
   success on the chapters you targeted).
2. Report a table: chapter | facts state | schematic state | rounds used |
   flow fixes applied | parked reason.
3. **Human-in-the-loop gate:** show `git diff --stat` (plus every flow-fix
   diff) and ask before committing. Never push without an explicit instruction.

## Guardrails (restate to yourself before starting)

- Never modify anything under `corpora/*/source/` — corpus material is read-only.
- Subagents are repo-read-only; every repo write goes through you, serially.
- Never hand-write facts content yourself: content flows only
  author → result JSON → `--set-facts`. If a chapter needs different facts,
  that's a new author round, not an orchestrator edit.
- `--accept-drift` on facts re-blesses content as-is; prefer re-authoring
  unless a human reviewed the stale content.
