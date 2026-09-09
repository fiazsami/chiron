# chiron

chiron mounts any git repo — a documented course or an undocumented codebase —
as a **corpus** and extracts its **linguistic structure**: the lexicon (what
things are called here), the phrasebook (how to say it when instructing an
agent), and the concept relations (how the names relate). The extracted
substrate is what you study: you learn to articulate — and to prompt any
coding agent — in the corpus's own terms, and a learning agent in the local
web viewer coaches you while you calibrate.

The operating theory: every repository has a working language, and
instructions phrased in that language land where generic phrasings drift.
chiron turns that language into grounded, drift-tracked data. See
[methodology/README.md](methodology/README.md) for the full theory and the
modular plan each dimension follows.

## Quickstart

```bash
/mount <repo-url>                  # in Claude Code: clone, plan, build the adapter
/translate <name>/v1               # author the register's linguistic structure
uv run python -m tools.lingua      # rebuild pages + manifest any time
cd web && npm run dev              # browse at localhost:3000, chat with the coach
```

## Layout

```
corpora/<name>/                    # one mounted corpus (gitignored in full —
  corpus.yaml                      #   corpora live only on your machine)
  source/                          # the checkout — read-only, shared by registers
  v1/                              # a register: one retelling of the material
    translation.yaml               # label, modes, notes, optional groups/adapter
    tools/adapter.py               # scan(cfg, root) -> Corpus (usually 4 lines)
    data/lexicon.yaml              # machine-owned — written only by `set`
    data/phrasebook.yaml
    data/relations.yaml
    pages/                         # generated Markdown (chapters + indexes)
corpora/.manifest.json             # version 6 — the viewer/agent's index
methodology/                       # the modular extraction plans (ship with repo)
tools/lingua/                      # the extraction pipeline
web/                               # viewer + learning agent (Claude Agent SDK)
```

Each **register** (`v1/`, `v2/`, …) is one retelling of the same source under
its own translation requirements; re-running `/mount` on a mounted corpus
creates the next one. Chapter ids are `<corpus>/<vN>/<group>/<NN>`.

## Vocabulary

| chiron says | not |
|---|---|
| corpus | course, project |
| register | iteration, version |
| chapter | lesson |
| group | tier, module, section |

The vocabulary is load-bearing — the same slugs name translation modes,
methodology documents, dimension modules, and manifest keys.

## How extraction stays honest

Every lexicon entry, phrase, and relation edge carries **anchors**: verbatim
quotes from the chapter's files, verified mechanically on write
(`uv run python -m tools.lingua set …` rejects a quote it cannot find) and
pinned to the chapter's `content_hash`. When the source changes, exactly the
affected anchors go stale; `status` shows where, `/translate` re-authors, and
`accept-drift` re-blesses only when you say so.

Corpora are yours: they are gitignored wholesale, so back up `v<N>/data/` if
the extraction matters to you — it is the only hand-won artifact.

## CLI

```bash
uv run python -m tools.lingua                 # build pages + manifest
uv run python -m tools.lingua check --strict  # drift gate (CI-friendly)
uv run python -m tools.lingua status --json   # per-chapter, per-dimension states
uv run python -m tools.lingua extract <id>    # authoring bundle for agents
uv run python -m tools.lingua set <dim> <id> --from payload.json
uv run python -m tools.lingua accept-drift <id> [--mode <dim>]
```
