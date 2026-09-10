# chiron

chiron mounts any git repo — a documented course or an undocumented codebase —
as a **corpus** and extracts its **linguistic structure**: the lexicon (what
things are called here), the phrasebook (how to say it when instructing an
agent), and the concept relations (how the names relate). The extracted
substrate is what you study: you learn to articulate — and to prompt any
coding agent — in the corpus's own terms. You browse the evidence in the local
web viewer, and you practise the language in Claude Code, where `/ch:calibrate`
grades your instructions against the substrate rather than against an opinion.

The operating theory: every repository has a working language, and
instructions phrased in that language land where generic phrasings drift.
chiron turns that language into grounded, drift-tracked data. See
[methodology/README.md](methodology/README.md) for the full theory and the
modular plan each dimension follows.

## Quickstart

```bash
/ch:mount <repo-url>       # in Claude Code: clone, generate docs if the repo
                           #   has none, plan, build the adapter
/ch:translate <name>/v1    # author the register's linguistic substrate
/ch:verify <name>/v1       # where it stands, and triage if an apply bounced
/ch:calibrate <name>/v1    # practise the language until it transfers
./ch where                 # one line: state + the next action
cd web && npm run dev      # browse the evidence at localhost:3000
```

The four verbs come from a plugin this repo ships and declares itself:
`.claude-plugin/marketplace.json` publishes the `chiron` marketplace,
`plugins/ch/` is the plugin, and `.claude/settings.json` enables `ch@chiron`
for anyone working in this project. There is nothing to install by hand — on
a fresh machine Claude Code asks for install consent the first time, and
`claude plugin install ch@chiron --scope project` does it non-interactively.

After editing anything under `plugins/ch/`, refresh the installed copy:

```bash
claude plugin uninstall ch --scope project && claude plugin install ch@chiron --scope project
```

(`claude plugin marketplace update` will not re-copy while the version in
`plugins/ch/.claude-plugin/plugin.json` is unchanged.)

`./ch` is the CLI, scoped: `./ch status` == `uv run python -m tools.lingua
status`. Both work, both from the repo root.

## Layout

```
chiron.yaml                        # declares the layout below; `./ch devenv` resolves it
devenv/                            # the development environment — gitignored in
                                   #   full, so it lives only on your machine
  reference/<name>/                # one mounted corpus
    corpus.yaml
    source/                        # the checkout — read-only, shared by registers
    derived/<recipe>/              # generated material — `./ch doc` writes it,
                                   #   git-committed, hashes like a checkout
    v1/                            # a register: one retelling of the material
      translation.yaml             # label, modes, notes, material, optional
                                   #   groups/adapter
      tools/adapter.py             # scan(cfg, root) -> Corpus (usually 4 lines)
      data/lexicon.yaml            # machine-owned — `author --apply` / `set` only
      data/phrasebook.yaml
      data/relations.yaml
      pages/                       # generated Markdown (chapters + indexes)
      work/                        # authoring runs and calibration log
      chroma/                      # optional local vector store (`./ch chroma`)
  reference/.manifest.json         # version 6 — the viewer/agent's index
  workspace/<name>/                # a repo a refined prompt gets applied to —
                                   #   scaffolded, not yet wired to any verb
methodology/                       # the modular extraction plans (ship with repo)
tools/lingua/                      # the extraction pipeline
web/                               # viewer: browse the evidence
```

**Two rooms.** You read a *reference* corpus to construct an instruction in that
repo's own working language, then apply it in a *workspace* repo you edit. Only
`reference/` is scanned; anything else under `devenv/` is a stray and
`./ch devenv` says so. See `AGENTS.md` for the full contract.

Each **register** (`v1/`, `v2/`, …) is one retelling of the same source under
its own translation requirements; re-running `/ch:mount` on a mounted corpus
creates the next one. Chapter ids are `<corpus>/<vN>/<group>/<NN>`.

## Vocabulary

| chiron says | not |
|---|---|
| devenv | corpora dir, env, sandbox |
| reference | corpora, sources |
| workspace | target, project, scratch |
| corpus | course, project |
| register | iteration, version |
| chapter | lesson |
| group | tier, module, section |
| entry | bit, card, item |
| dimension | mode (outside `translation.yaml`), dim |
| calibration | studying, practice |

The vocabulary is load-bearing — the same slugs name translation modes,
methodology documents, dimension modules, and manifest keys.

## How extraction stays honest

Every lexicon entry, phrase, and relation edge carries **anchors**: verbatim
quotes from the chapter's files, verified mechanically on write
(`./ch set …` rejects a quote it cannot find) and
pinned to the chapter's `content_hash`. When the source changes, exactly the
affected anchors go stale; `./ch where` shows what to do, `/ch:translate` re-authors, and
`accept-drift` re-blesses only when you say so.

Corpora are yours: `devenv/` is gitignored wholesale, so back up `v<N>/data/` if
the extraction matters to you — it is the only hand-won artifact.

## CLI

```bash
./ch                          # build pages + manifest
./ch where                    # state + next action, per register
./ch devenv                   # where reference/ and workspace/ resolved to
./ch resolve <target>         # what a target expression expands to
./ch check --strict           # drift gate (CI-friendly)
./ch status --json            # per-chapter, per-dimension states
./ch extract <id>             # authoring bundle for agents
./ch set <dim> <id> --from payload.json
./ch accept-drift <id> [--dimension <dim>]

# Generated material — the one verb that needs Docker. An undocumented repo
# has a working language but no prose to anchor it to; a doc generator emits
# the missing half. Runs in a pinned container with no network and a
# read-only source, and proves the output is reproducible before keeping it.
./ch doc --census <corpus>              # what a generator would find here
./ch doc --stage <corpus> --from r.json # generate, normalize, prove
./ch doc --promote <corpus>/<recipe>    # keep it: devenv/reference/<name>/derived/<recipe>/
./ch doc --status                       # derived trees behind their source

# Study — read-only, graded against data/*.yaml, no LLM in the loop.
./ch ask <register> "<text>"          # what is this called here
./ch ask <register> --relate <a> <b>  # how two names relate
./ch grade <register> --text "…"      # does this instruction land (exit 0/1)

# API-native authoring (what /ch:translate drives): Batch API + structured
# outputs on a Sonnet-class model; results apply through the same
# grounded validate/set path. Model/effort via --model/--effort or
# CHIRON_AUTHOR_MODEL / CHIRON_AUTHOR_EFFORT.
./ch author <register|group|ids> [--sync]
./ch author --collect --wait
./ch author --apply [--check]
./ch author --status          # run health, cascades, the ordered retry set
./ch author --retry <id>
```
