---
name: mount
description: >
  Mount a learning resource (a git repo or local folder) as a versioned
  corpus register: clone it under devenv/reference/<name>/source/, gather the
  translation requirements, plan the extraction interactively, author the
  register's adapter in devenv/reference/<name>/v<N>/tools/adapter.py, and build its
  pages. Re-running it on a mounted corpus creates the next register — a
  fresh retelling of the same material. Args: a git URL or local path,
  optionally a corpus name; or a mounted corpus name to add a register; with
  no args, lists incomplete mounts. Mounting is deliberately interactive —
  the gates are where the learner's requirements enter the system.
---

Read `../GRAMMAR.md` first. You are mounting a corpus register. Run
everything from the repo root.

A corpus is `devenv/reference/<name>/`: `corpus.yaml`, one shared `source/`, and one
or more registers `v1/`, `v2/`, … — each a distinct retelling under its own
`translation.yaml`. All of it is gitignored; the repo ships tooling only.
`README.md` has the layout; do not restate it to the user unless asked.

**Building the adapter is the learning exercise, and the result belongs to
the learner.** After mounting they maintain it, rebuild after edits, and back
up `devenv/reference/` themselves.

## Invariants

- A mount always lands in the reference room. Never write anything under
  `devenv/workspace/` — that room belongs to the apply half, which no verb
  drives yet. Resolve the rooms with `./ch devenv`; never hardcode them.
- Never modify anything under `devenv/reference/*/source/`.
- Never delete or overwrite anything under `devenv/reference/` without an explicit yes.
- A derived tree is generated: regenerate it, never edit it. `./ch doc` is its
  only writer, and `.chiron/recipe.yaml` is how it is reproduced.
- Never run a container by hand. `./ch doc` builds the invocation from a
  validated recipe; that is what keeps a proposed recipe out of a shell.
- The adapter is stdlib + pyyaml only: deterministic, no network, writes
  nothing. Adapters are register-agnostic — the pipeline stamps the register on.
- `corpus.yaml` is written once per corpus; never edit it for a new register.
- Registers are append-only: creating `v<N+1>` never edits an older register's
  `translation.yaml`, adapter, or `data/`.
- Never share or copy `data/` between registers.
- One `source/` per corpus — never a second checkout under a register.
- Group ids `lexicon`, `phrasebook`, `relations`, `concept-relations`, `chat`,
  `api`, `assets` are reserved; the build rejects them.
- If material genuinely does not fit the group/chapter shape, say so and
  discuss options — never force a bad mapping.

## Target

`/ch:mount` takes a **source** expression as well as a target, because it is
the verb that creates targets.

| Args | Means |
|---|---|
| `<url>` or `<path>` `[name]` | mount a new corpus — or a new register, if the origin already resolves to a mounted one |
| `<corpus>` | the next register of a mounted corpus |
| `<corpus>/<vN>` | resume or re-mount that register |
| *(nothing)* | `./ch where` — list incomplete mounts and stop |

Classify the first token: `://` or scp-like (`user@host:path`) → URL; an
existing directory → local path (resolve to absolute); otherwise explain and
stop. Derive the default name from a URL as `<owner>-<repo>` (last two path
segments, `.git` stripped); deeper nesting defaults to the last two with the
full join offered as an alternative; a local path uses its basename. Sanitize
to `^[a-z0-9][a-z0-9-]*$`, and never `^v[0-9]+$`.

Then check what already exists, before creating anything:

- **Same origin already mounted** (any `devenv/reference/*/corpus.yaml`) → that IS this
  corpus, whatever its name. Gate A offers the next register, or a source pull
  plus rebuild.
- **Name taken by a complete corpus** → Gate A offers `v<N+1>`, or a pull and
  rebuild, or stop.
- **`corpus.yaml` and a register but no `source/`** → re-mount: recreate
  `source/` from `origin` (confirm if it disagrees with the arg) and go
  straight to Loop 4.
- **A partial tree** → resume the missing pieces.
- **Anything else under that name** → refuse it; take another name at Gate A.

## Loop

1. **Orient.** `./ch where`.
2. **Source in place** (only if `devenv/reference/<name>/source/` is absent). URL →
   `git clone <url> devenv/reference/<name>/source`. Local directory →
   `ln -s <absolute-path> devenv/reference/<name>/source` — never copy. A plain
   non-git folder is fine; the pipeline falls back to content digests. For a
   new register, reuse the checkout; a pull flags older registers' changed
   chapters stale, which is honest.
3. **Generate the material** — only when the source is code-shaped and
   prose-poor, and only for a new register. A documented repo already has the
   material; generating beside it buys scaffolding, not vocabulary.

   ```
   ./ch doc --census <name>          # what a generator would find here
   ```

   The census prints the language mix, doc-comment density, the prose ratio,
   and the closed list of tools with their options. If it names no candidate,
   or the prose ratio is already high, say so and go to step 4 against
   `source/` — that is the common case and it is not a failure.

   Otherwise, spawn `ch:docgen-planner` with the corpus name and a scratchpad
   path. It reads the census, reads the source, and writes one recipe JSON.
   You do not ask the user which tool: the selection is the agent's, and the
   user meets it at the gate with the output in front of them.

   ```
   ./ch doc --stage <name> --from <recipe.json>
   ```

   Staging pulls the pinned image, runs the generator with no network and a
   read-only source, normalizes the output, and — for a recipe not yet proved
   — generates a second time and compares. Non-identical bytes fail here, and
   that is the right place: every anchor is pinned to a chapter's
   `content_hash`, so a generator that varies would mark the whole register
   stale on every regeneration.

   Then **GATE M**, then on approval:

   ```
   ./ch doc --promote <name>/<recipe>
   ```

   The register you write in step 5 names it: `material: derived/<recipe>`.
4. **Explore, then gate.** Read the layout, how material is grouped and
   ordered, per-document structure, and what should be skipped. Read
   representative *documents*, not just listings. Classify the shape:
   - **markdown course** (`<group>/<NN>-doc.md`) → delegate to
     `tools.lingua.sources.markdown`.
   - **a derived tree** (you ran step 3) → delegate to
     `tools.lingua.sources.apidoc`. Its knobs are `group_by` (`directory`, one
     chapter per page; `module`, one per module directory) and `max_chapters`,
     both defaulting to the recipe's own.
   - **code repo** → delegate to `tools.lingua.sources.codetree`. Its
     chaptering is deterministic: groups = top-level directories; chapters =
     immediate subdirectories, plus a `<group>-files` chapter for loose files;
     root files form a `root` group. Knobs live under `adapter:` in
     translation.yaml — `include` globs (replace the default extension
     filter), `exclude` globs, `depth: 1|2`.
   - **neither** → a fresh adapter.

   Your references are the framework itself; a fresh fork ships no corpus
   artifacts, so never assume any exist: `tools/lingua/model.py` (the
   `Corpus`/`Group`/`Chapter` contract, chapter kinds, reserved ids),
   `tools/lingua/translation.py` (the translation.yaml contract, implemented
   vs recorded modes), `tools/lingua/sources/markdown.py` and
   `sources/codetree.py` (complete worked examples), `tools/lingua/gittree.py`
   (`git_tree`, `sha256_file`, `source_version`, `check_workdir` — hash
   committed blobs, not working-tree bytes), `methodology/README.md`. Any
   locally mounted `devenv/reference/*/v*/tools/adapter.py` is a bonus example — use it
   opportunistically, never require it.

   Then **Gate B**.
5. **Write the tools.**
   - `devenv/reference/<name>/corpus.yaml` (new corpus only): `title` (required, the
     one approved), `origin` if cloned, `urls` when known.
   - `devenv/reference/<name>/v<N>/translation.yaml`: `label`, `modes` (from Gate B,
     required), `notes` (the gathered requirements, verbatim intent),
     `material: derived/<recipe>` when step 3 promoted one, plus `groups` or
     `adapter` only when needed.
   - `devenv/reference/<name>/v<N>/tools/adapter.py` — `scan(cfg, root) -> Corpus`.
     A delegation is four lines:

     ```python
     from tools.lingua.sources import markdown

     def scan(cfg, root):
         return markdown.scan(cfg, root)
     ```

     A fresh adapter reuses the shared helpers rather than re-implementing
     extraction, reads name/title/urls/groups from `cfg`, keeps only layout
     knowledge, and computes a stable 12-hex `content_hash` per chapter — it
     pins every anchor's `curated_against`. In Build-together mode, write in
     logical blocks (group discovery → chapter loop → hashing), explaining
     each and confirming before the next: checkpoints, not a line-by-line quiz.
6. **Make the scan succeed.** Iterate `./ch status` until the chapter list
   looks right — ids, groups, titles, kinds. Spot-check `./ch extract <id>`:
   the bundle should show the Translation requirements section and one
   Methodology section per selected dimension. If it will not converge after a
   few attempts, stop and bring the mismatch to the user rather than forcing it.
7. **Build.** `./ch`, then review the summary and a couple of pages under
   `devenv/reference/<name>/v<N>/pages/`.

## Gates

```
GATE A — scope
  fires         after the target is classified, before anything is created
  what changes  creates devenv/reference/<name>/v<N>, or reuses an existing corpus
  the material  the derived name, what already exists under it, the source
                origin and whether it is about to be pulled
  branches      mount as devenv/reference/<name>/v<N> · add a register to an existing
                corpus · pull source and rebuild instead · another name · stop
  reversibility reversible — nothing is written until it closes
  unattended    stop and report
```

For a new register of an existing corpus, ask instead **"What should this
register do differently?"** (free text encouraged) — the answer seeds `label`
and `notes`. A re-mount, where name and label already exist, may skip Gate A.

```
GATE M — material
  fires         after staging, before anything is promoted under devenv/reference/<name>/
  what changes  creates devenv/reference/<name>/derived/<recipe>/ and makes it this
                register's material — the chapters Gate B then plans over
  the material  ALL of it, inline; the census and the recipe are not enough
                on their own, because the question is what the generator
                actually produced:
                · the census — languages, file counts, doc-comment density,
                  prose ratio
                · the chosen tool, and the recipe's options verbatim
                · the image, digest-pinned as `./ch doc --stage` reported it
                · the determinism result: "identical", or the exact first
                  difference between the two runs
                · the projected group/chapter mapping WITH the chapter count
                  — `./ch doc --stage` prints it, run through the same adapter
                  the register will use, so it is the real number
                · ONE staged page in full, pasted — not a path, not a summary.
                  Pick a representative one, not the shortest
  branches      promote and mount against it —
                  `./ch doc --promote <name>/<recipe>`
                · mount against source/ instead, skipping generation —
                  continue at Loop 4
                · re-plan with a different tool — re-run ch:docgen-planner
                · adjust the options and re-stage —
                  `./ch doc --stage <name> --from <recipe.json>`
                · stop — `./ch doc --clean <name>/<recipe>`
  reversibility reversible — staging lives in devenv/reference/<name>/.staging/, which
                nothing scans, and nothing is promoted until this closes
  unattended    stop and report
```

Say the chapter count out loud at this gate. Every chapter is one authoring
request, so the count is what the next `/ch:translate` will cost, and it is
the number most likely to send the user back to a narrower recipe.

If staging reported a determinism failure there is no promote branch: show the
difference, and offer only re-plan, narrow, or mount against `source/`.

```
GATE B — plan
  fires         after exploring the source, before writing any code
  what changes  the register's dimensions, its adapter, and its chaptering
  the material  BOTH halves, stated before any code exists:
                · extraction plan — display title, what becomes a group
                  (ordered, labeled), what becomes a chapter (id/number/slug
                  rules, kind doc|code, which files make a code chapter),
                  where title and description come from, what is skipped.
                  For a codetree or apidoc delegation show the resulting
                  group/chapter mapping explicitly — confirming the chaptering
                  IS this gate.
                · translation plan — the register's label and notes text, and
                  which dimensions it extracts: lexicon (what things are
                  called here), phrasebook (how to say it when instructing an
                  agent), concept-relations (how the names relate), or a
                  custom slug recorded for later. A dimension not selected is
                  not tracked at all — no coverage pressure, no data file.
                  Phrasebook and concept-relations reference lexicon slugs, so
                  selecting either without lexicon is almost always a mistake;
                  say so if it happens.
  branches      Approve with best-fit delegation (default — delegate to a
                shipped building block when the source fits) · Author fresh
                (purpose-built either way; building it is the exercise) ·
                Build together (pair on it) · Revise the plan
  reversibility APPEND-ONLY (permanent) for the dimension set: a register's
                dimensions are fixed once data is authored against it. Adding
                one later means a new register. Say this at the gate.
  unattended    stop and report
```

For a pure delegation the plan is short — present it anyway; the gate is the
point.

## Report

Per `GRAMMAR.md`. New registers start with every tracked state `none` — that
is normal, say so. Include chapters per group, chapter kinds, and each mode's
status (active, or recorded and not yet implemented).

Then hand over ownership — nothing is committed; `devenv/` is gitignored and
lives only on this machine:

- **The adapter is yours**: edit `devenv/reference/<name>/v<N>/tools/adapter.py`,
  rebuild with `./ch`.
- **Update the material**: `git -C devenv/reference/<name>/source pull`, then rebuild —
  changed chapters flag their anchors stale, in every register. For a
  generated register, pull and then re-stage: `./ch doc --status` tells you
  when a derived tree is behind its source, which nothing else can see.
- **Author**: `/ch:translate <name>/v<N>` fills the lexicon, phrasebook and
  concept relations. `data/` is the register's accumulated value.
- **Study**: `/ch:calibrate <name>/v<N>` once there is substrate to work.
- **Iterate**: `/ch:mount` the same corpus again for `v<N+1>`.
- **Browse**: `cd web && npm run dev`.
- **Back up `devenv/reference/` yourself** — each register's `data/` especially.

Finish by asking what to do next, with explicit targets. Asking now rather
than up front is deliberate: the user could not have known the size of the
job before Gate B.
