# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd prime` for full workflow context.

> **Architecture in one line:** Issues live in a local Dolt database
> (`.beads/dolt/`); cross-machine sync uses `bd dolt push/pull` (a
> git-compatible protocol), stored under `refs/dolt/data` on your git
> remote — separate from `refs/heads/*` where your code lives.
> `.beads/issues.jsonl` is a passive export, not the wire protocol.
>
> See [SYNC_CONCEPTS.md](https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md)
> for the one-screen overview and anti-patterns (don't treat JSONL as the
> source of truth; don't `bd import` during normal operation; don't
> reach for third-party Dolt hosting before trying the default).

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work atomically
bd close <id>         # Complete work
bd dolt push          # Push beads data to remote
```

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

## chiron

chiron mounts any git repo as a **corpus** and extracts its **linguistic
substrate** — the lexicon (what things are called here), the phrasebook (how
to say it when instructing an agent), and the concept relations (how the names
relate). See `README.md` for the layout and `methodology/README.md` for the
theory.

The interaction language has one spine, one grammar, one gate shape and one
voice. This section is the single home for all four: skills and agent prompts
reference it, they do not restate it.

### The development environment

chiron is a development environment for prompting, and it has two rooms. You
read a **reference** corpus to construct an instruction in that repo's own
working language, then apply it in a **workspace** repo you actually edit —
two different relationships to a checkout, so two directories, not one.

```
chiron.yaml           declares the layout; delete it and the defaults below stand
devenv/               the root — gitignored in full, on this machine only
  reference/<name>/     a mounted corpus (see Layout in README.md)
  workspace/<name>/     a repo a refined prompt gets applied to
```

`tools/lingua/devenv.py` is the only place that resolves these paths, and
`./ch devenv` prints what they resolved to — read it, never assume the strings.
A room is one directory name inside the root (`^[a-z0-9][a-z0-9-]*$`), never a
path and never absolute; the loader rejects anything else. Override the root
per machine with `CHIRON_DEVENV`.

Discovery only ever scans `reference/`. A checkout dropped anywhere else under
the root is not half-mounted, it is invisible — `./ch devenv` and `./ch check`
name it as a stray rather than leaving you to wonder.

**Workspace is a scaffold.** It has a directory, a config key, validation and a
read-only CLI surface, and nothing else yet. No verb mounts into it and no verb
edits it. Building that half is the next piece of work.

### The verb spine

| Verb | Reading | Writes | Owns |
|---|---|---|---|
| `/ch:mount` | production | `corpus.yaml`, `translation.yaml`, `tools/adapter.py`, `derived/`, `pages/` | getting material in |
| `/ch:translate` | production | `data/*.yaml` — **the single writer** | authoring and repairing the substrate |
| `/ch:verify` | production | nothing | where a register stands, and triage |
| `/ch:calibrate` | study | `work/calibration.jsonl` only | the learner's own language |

`./ch` is the CLI, scoped: `./ch status` == `uv run python -m tools.lingua
status`. Both work; both run from the repo root. `./ch where` is the one-move
answer to "where am I"; `./ch devenv` is the one-move answer to "where does
anything live".

`./ch doc` belongs to `/ch:mount`'s column — generating documentation from a
corpus's code *is* getting material in. It is the one verb that needs Docker;
nothing else in chiron does. `/ch:verify` reads `./ch doc --status` and writes
nothing, as always.

### Targets

Every verb and every subcommand acts on a target. One grammar, one
implementation (`tools/lingua/resolve.py`), checkable with `./ch resolve`:

```
(nothing)                    the caller's stated default
all                          every register, one selection each
<corpus>                     a corpus, when it has exactly one register
<corpus>/<vN>                a register
<corpus>/<vN>/<group>        a group
<group>/<NN>                 a chapter, when one mounted register matches
<corpus>/<group>/<NN>        a chapter, when the corpus has one register
<corpus>/<vN>/<group>/<NN>   a chapter, always unambiguous
```

`/ch:mount` additionally accepts a **source** expression (a git URL or local
path), because it is the one verb that creates targets rather than consuming
them.

### Vocabulary

Load-bearing: the same slugs name dimensions, methodology documents, dimension
modules, and manifest keys. One word per concept in anything a human reads.

| Concept | Say | Not |
|---|---|---|
| a projection of the working language | **dimension** | mode, dim |
| a register's election of one | **mode** — only as the `translation.yaml` key | — |
| addressable dimension name | `lexicon` / `phrasebook` / `concept-relations` | abbreviations |
| count nouns | terms / phrases / relations | edges (a data key only) |
| one addressable unit of substrate | **entry** | bit, card, item |
| a retelling of the material | **register** | iteration, version |
| the tree a register scans | **material** — the `translation.yaml` key | input, corpus dir |
| generated material | `derived/<recipe>` | docs, apidocs, generated/ |
| how a derived tree was produced | **recipe** | config, profile |
| the learner's activity | **calibration** | studying, practice |
| corpus / chapter / group | as written | course, lesson, tier |
| the whole two-room tree | **devenv** | corpora/, env, sandbox |
| the room corpora mount into | **reference** | corpora, sources |
| the room prompts are applied in | **workspace** | target, project, scratch |

`--dimension` is the flag; `--mode` still works as a silent alias.

### States

`ok` = every anchor pinned to the chapter's current `content_hash` ·
`stale` = the chapter changed since these entries were anchored ·
`none` = no entries anchored here. Computed, never stored
(`tools/lingua/status.py`). Register state is worst-of-chapters.

A relations `stale` can also mean a dangling endpoint — a term slug left the
lexicon. `accept-drift` will not fix that one; re-authoring will.

### Invariants

Each is enforced somewhere; the pointer is the drift test.

- A corpus lives in `devenv/reference/` and nowhere else. The layout is
  declared in `chiron.yaml` and resolved in one place
  (`tools/lingua/devenv.py`); read it with `./ch devenv` rather than
  hardcoding a path. Anything else under the root is a stray, and both
  `./ch devenv` and `./ch check` say so.
- Never modify anything under `devenv/reference/*/source/` — read-only material, and it
  may be someone else's licensed work. `./ch doc` binds it into the container
  read-only, so for generation the kernel enforces this rather than the tooling.
- `devenv/reference/*/derived/<recipe>/` is generated: regenerate it, never edit it.
  `./ch doc` is its only writer, and its `.chiron/recipe.yaml` is how it is
  reproduced. Each derived tree is its own git checkout, so it hashes and
  versions exactly like `source/`.
- A generator runs only from a validated recipe, never from a command an agent
  composed. The tool registry (`tools/lingua/docgen/__init__.py`) is closed.
- Nothing is promoted out of `.staging/` until it has generated twice with
  identical bytes. Anchors are pinned to generated bytes, so a generator that
  varies would mark a whole register stale on every run.
- `data/*.yaml` is machine-owned: written only by `./ch author --apply` and
  `./ch set` — never by hand (`tools/lingua/dimensions/base.py`).
- `pages/` and `devenv/reference/.manifest.json` are generated; rebuild, never edit
  (`tools/lingua/render.py`, `tools/lingua/manifest.py`).
- One `--apply` at a time — it is the single writer (`tools/lingua/author.py`).
- Registers are append-only: creating `v<N+1>` never edits an older register.
- Never share or copy `data/` between registers — each retelling is extracted
  against its own requirements.
- Never delete or overwrite anything under `devenv/reference/` without an explicit yes.
- `accept-drift` re-blesses content as-is; prefer re-authoring unless a human
  reviewed the stale content.
- Anchors are verbatim and mechanically verified; drift pins are per-anchor
  (`curated_against`).

### Gates

Every human decision states five fields. **A gate that cannot show its
material is a bug, not a gate.**

```
GATE <name>
  what changes   one sentence, in the target's own ids
  the material   both sides, inline, verbatim — never a pointer to go read
  branches       each with its exact runnable command
  reversibility  reversible | re-runnable | append-only (permanent)
  unattended     what happens when nobody is there to answer
```

### Contracts — change in lockstep or not at all

`chiron.yaml`'s `devenv:` keys (with `tools/lingua/devenv.py` and the
reference path in `web/lib/content.ts`), `devenv/reference/.manifest.json` v6 keys
(with `web/lib/content.ts`), `status --json`
keys, extract-bundle headings and `<<<BEGIN x>>>` sentinels, `data/*.yaml`
keys, `translation.yaml` `modes:` and `material:`, the docgen recipe schema
(with `containers/docgen/entrypoint.py` and the image's
`org.chiron.recipe-schema` label), the enums (`ok|stale|none`, the six term
kinds, the eight relation types), and the reserved group ids. Each
methodology doc's "Schema and caps" section mirrors its dimension's
`validate_payload`.

## Build & Test

```bash
./ch check                               # pipeline drift report, writes nothing
./ch where                               # state + next action, per register
./ch doc --status                        # derived trees behind their source
docker build -t chiron-docgen:dev containers/docgen/   # only ./ch doc needs it
uv run python -m pytest tests/ -q        # test suite (tmp_path fixtures only)
python3 -m compileall -q tools           # syntax check
cd web && npm run build                  # type-checks the viewer + manifest contract
```

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
