# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->


## Build & Test

```bash
uv run python -m tools.lingua check      # pipeline drift report, writes nothing
uv run python -m pytest tests/ -q       # pipeline test suite (tmp_path fixtures only)
python3 -m compileall -q tools           # syntax check
cd web && npm run build                  # type-checks the viewer + manifest contract
```

## Architecture Overview

chiron mounts any git repo as a **corpus** under `corpora/<name>/` (gitignored
in full — corpora live only on the learner's machine). Each **register**
(`v1/`, `v2/`, …) is one retelling under its own `translation.yaml`; a
per-register `tools/adapter.py` scans `source/` into the `Corpus`/`Chapter`
model (`tools/lingua/model.py`), the pipeline extracts linguistic dimensions
(lexicon, phrasebook, concept-relations) into machine-owned `data/*.yaml`,
renders `pages/` plus `corpora/.manifest.json` (version 6), and `web/` serves
them at `/[corpus]/[register]/…` with a Claude Agent SDK learning agent.
See README.md for the full layout; methodology/README.md for the theory and
the dimension = mode slug = methodology doc = dimension module contract.

## Conventions & Patterns

- Vocabulary is load-bearing: corpus (not course), register (not iteration),
  chapter (not lesson), group (not tier). Chapter ids are
  `<corpus>/<vN>/<group>/<NN>`.
- `corpora/*/source/` is read-only material; `pages/` is generated;
  `data/*.yaml` is machine-owned via `uv run python -m tools.lingua set` —
  never hand-edit any of them. Anchor quotes are verbatim and mechanically
  verified; drift pins are per-anchor (`curated_against`).
- The manifest v6 keys, extract-bundle headings, and `status --json` keys are
  contracts shared by `tools/lingua/`, `web/lib/content.ts`, and
  `.claude/agents/*.md` — change them in lockstep or not at all. Each
  methodology doc's "Schema and caps" section mirrors its dimension's
  `validate_payload` — change those together too.
- Group ids `lexicon`, `phrasebook`, `relations`, `concept-relations`,
  `chat`, `api`, `assets` are reserved (they would shadow viewer routes);
  the build rejects them.
