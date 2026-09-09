---
name: mount
description: >
  Mount a learning resource (a git repo or local folder) as a versioned
  corpus register: clone it under corpora/<name>/source/, gather translation
  requirements, plan the extraction interactively, author the register's
  adapter in corpora/<name>/v<N>/tools/adapter.py, and build its pages.
  Re-running /mount on a mounted corpus creates the next register — a fresh
  retelling of the same material. Args: a git URL or local path, optionally
  followed by a corpus name. Mounting is deliberately interactive — the form
  and the plan gate are where the learner's requirements enter the system.
---

You are mounting a corpus register into chiron. The repo root is the
project root (where `tools/` and `corpora/` live); run all commands from
there.

A mounted corpus is a directory `corpora/<name>/` holding corpus-level facts
plus one or more **registers** — `v1/`, `v2/`, ... — each a distinct
retelling of the same material, translated per its own requirements.
Everything under `corpora/` is gitignored — the repo ships tooling only, and
corpus artifacts live only on this machine:

- `corpus.yaml` — corpus-level: title, urls, origin (written once)
- `source/` — the cloned repo or a symlink — ONE per corpus, shared by all
  registers
- `v<N>/translation.yaml` — the register's translation requirements: label,
  modes (the linguistic dimensions to extract), free-text notes, optional
  groups override, optional adapter knobs
- `v<N>/tools/adapter.py` — YOUR main deliverable: `scan(cfg, root) -> Corpus`
- `v<N>/data/` — the extracted linguistic structure: `lexicon.yaml`,
  `phrasebook.yaml`, `relations.yaml` — machine-owned, written only by
  `uv run python -m tools.lingua set ...`
- `v<N>/pages/` — generated pages, created by the build

Content flows in two stages: the deterministic adapter scans the source and
the build renders pages plus the manifest (served by `web/`); the LLM
authoring passes (`/translate`) then fill the register's linguistic
structure — lexicon, phrasebook, concept relations — pinned to each
chapter's content hash via verbatim quote anchors, so drift is tracked per
chapter. Registers let a learner explore different retellings of the same
material side by side.

Building the adapter is the learning exercise, and the result belongs to the
learner: after mounting they maintain it, rebuild after edits, and back up
`corpora/` themselves.

## 1. Setup

1. Parse args: first token is a git URL or local path; an optional second
   token is the corpus name. Classify: contains `://` or is scp-like
   (`user@host:path`) → URL; an existing directory → local path (resolve to
   absolute); anything else → explain and stop.
2. Derive the default name — descriptive, so it won't collide or ambiguate:
   - URL: strip trailing `/` and `.git`, split the path part; join the last
     two segments as `<owner>-<repo>`
     (`https://github.com/fewshot-works/academy.git` →
     `fewshot-works-academy`). Hosts with deeper nesting (GitLab subgroups):
     default to the last two segments, offer the full-path join as the
     alternative. A single-segment path → use it alone.
   - Local path: the directory basename.
   Sanitize: lowercase, squash runs outside `[a-z0-9]` to `-`, trim `-`; the
   result must match `^[a-z0-9][a-z0-9-]*$` and must NOT match `^v[0-9]+$`
   (reserved for register dirs). If nothing valid survives, collect a name
   via the form's free-text answer.
3. Determine the target register and announce it as
   **`corpora/<name>/v<N>`** — N is 1 for a fresh corpus, else 1 + the
   highest existing `v<N>` under the corpus. Check prior state before
   creating anything:
   - Same origin URL already in some `corpora/*/corpus.yaml`? That IS this
     corpus (whatever its name) — proceed as a **new register** of it, or
     offer `git -C corpora/<that>/source pull` plus a rebuild if the user
     only wanted a refresh.
   - `corpora/<name>/` with corpus.yaml and ≥1 complete register → offer
     via the form: **new register** `v<N+1>` (the default), pull source +
     rebuild the existing registers, or stop.
   - corpus.yaml + a `v<N>/` with translation.yaml and adapter but
     `source/` missing (restored backup, fresh machine) → **re-mount**:
     recreate `source/` from `origin` (confirm first if it disagrees with
     the arg), run `uv run python -m tools.lingua status` to validate the
     existing adapters, then go to step 6.
   - Partial trees (`source/` but no corpus.yaml; a `v<N>/` with
     translation.yaml but no adapter) → **resume**: verify the checkout is
     healthy (`git -C corpora/<name>/source rev-parse HEAD` for clones;
     confirm with the user before deleting a broken partial clone), run the
     form if it never ran, and continue from wherever the mount stopped.
   - Anything else under that name → refuse it; pick another name via the
     form.

## 2. Orient with the form

One AskUserQuestion call, before any heavy work, with these three questions
(each option gets a short description; free-text "Other" is always
available):

1. **Name** — "Mount as `corpora/<derived>/v1`?" Options: the derived
   default (recommended), plus at most one sensible variant (the bare
   basename when it's valid and free, or the full-path join for nested
   hosts). Validate a free-text answer against `^[a-z0-9][a-z0-9-]*$` (not
   `^v[0-9]+$`) and re-run the step-1 checks. For a **new register** of an
   existing corpus the name is settled — instead ask "What should this
   register do differently?" (free-text encouraged); the answer seeds the
   register's `label` and `notes`.
2. **Dimensions** — "Which linguistic dimensions should this register
   extract?" (multiSelect):
   - Lexicon (`lexicon`, recommended) — what things are called here, with
     grounded definitions; see methodology/lexicon.md.
   - Phrasebook (`phrasebook`) — canonical phrasings for instructing an
     agent about this corpus; see methodology/phrasebook.md.
   - Concept relations (`concept-relations`) — typed links between terms;
     see methodology/concept-relations.md.
   - Other — free text; recorded as a custom mode slug in translation.yaml
     (no extraction machinery for it yet).
   Explain briefly: a dimension that isn't selected isn't tracked at all —
   no coverage pressure, no data file; phrasebook and concept-relations
   reference lexicon slugs, so selecting either without `lexicon` is almost
   always a mistake — say so if it happens.
3. **Next** — "After the build?"
   - Open the viewer (`cd web && npm run dev`).
   - Extract now (run `/translate <name>/v<N>` on the fresh chapters —
     always pass the explicit target so other corpora aren't swept in).
   - Stop there — report and hand over.

Honor the answers for the rest of the flow.

## 3. Get the source in place

Only if `corpora/<name>/source/` is absent:

- URL → `git clone <url> corpora/<name>/source`
- existing local directory → `ln -s <absolute-path> corpora/<name>/source`
  (never copy; never modify the target; a plain non-git folder is fine —
  the pipeline falls back to content digests)

For a new register, reuse the existing checkout; offer
`git -C corpora/<name>/source pull` first if the user wants the latest
material (pulling flags older registers' changed chapters stale, which is
honest and fine). One `source/` per corpus — never a second checkout under
a register.

## 4. Explore and plan the extraction (the interactive core)

Explore the source repo — directory layout, how material is grouped and
ordered, per-document structure (frontmatter, headings), what should be
skipped (indexes, setup pages, generated or vendored dirs). Read a handful
of representative documents or files, not just listings. Classify the
source's shape:

- A **markdown course** — `<group>/<NN>-doc.md` layout, one subdirectory per
  group of ordered docs → delegate to `tools.lingua.sources.markdown`.
- A **code repo** → delegate to `tools.lingua.sources.codetree`, and confirm
  its deterministic chaptering in the plan gate: groups = top-level
  directories; chapters = immediate subdirectories, plus a `<group>-files`
  chapter for files directly in the group directory; loose root files form a
  `root` group. Offer the `adapter:` knobs in translation.yaml — `include`
  globs replace the default source-extension filter, `exclude` globs add
  skips, `depth: 1|2` (1 = one chapter per group's whole subtree, 2 = per
  immediate subdir, the default).
- Neither shape fits cleanly → plan a fresh adapter.

Your references are the framework itself — a fresh fork ships no corpus
artifacts, so never assume any exist:

- `tools/lingua/model.py` — the target contract (`Corpus`, `Group`,
  `Chapter`), chapter kinds (`doc` | `code`), and the reserved group ids.
- `tools/lingua/translation.py` — the translation.yaml contract and the mode
  registry (implemented vs recorded).
- `tools/lingua/sources/markdown.py` — the generic markdown-course adapter;
  a complete worked example of the contract.
- `tools/lingua/sources/codetree.py` — the generic code-repo adapter and its
  `adapter:` knobs.
- `tools/lingua/gittree.py` — `git_tree`, `sha256_file`, `source_version`,
  `check_workdir` (hash committed blobs, not working-tree bytes).
- `methodology/README.md` — the operating theory and the modularity contract
  behind the dimensions.

If other registers or corpora happen to be mounted locally, their
`corpora/*/v*/tools/adapter.py` files are extra worked examples — use them
opportunistically, never require them.

Present the plan and get approval via AskUserQuestion before writing code.
The plan has two halves, both stated before any code exists:

- **Extraction plan**: the proposed display title (from the source README or
  site name), what becomes a group (ordered, labeled), what becomes a chapter
  (id/number/slug rules; kind `doc` or `code`; which files constitute a code
  chapter), where title/description come from, and what is skipped. For a
  codetree delegation, show the resulting group/chapter mapping explicitly —
  the chaptering confirmation is part of this gate.
- **Translation plan**: the register's `label` and `notes` text, and per
  selected dimension what is produced now versus authored later — the build
  scaffolds pages and the manifest now; lexicon, phrasebook, and
  concept-relations entries are authored by `/translate` and pinned to each
  chapter's `content_hash` via verbatim quote anchors; custom modes are
  recorded in translation.yaml, reported as not yet implemented.

The approval question folds in the adapter approach: **Approve with best-fit
delegation** (default — delegate to a shipped building block like the
markdown or codetree adapter when the source fits; author fresh only when
nothing fits), **Author fresh** (write a purpose-built adapter either way;
building it is the exercise), **Build together** (pair on it: explain each
block and confirm before writing the next), or **Revise the plan**. For a
pure delegation the plan is short — present it anyway; the gate is the point.

## 5. Build the tools

- Write `corpora/<name>/corpus.yaml` **only for a new corpus** (never edit
  it for a new register):

  ```yaml
  title: <Display Title>            # required — the one approved in the plan
  origin: <url>                     # if cloned
  urls: {site: ..., repo: ...}      # when known; drive page links
  ```

- Write `corpora/<name>/v<N>/translation.yaml`:

  ```yaml
  label: <one-line description of this retelling>   # optional but encouraged
  modes: [lexicon, phrasebook, concept-relations]   # from the form; required
  notes: |                                          # free-text requirements
    <the gathered translation requirements, verbatim intent>
  groups: [{id: ..., label: ...}]   # only if discovery order/labels need overriding
  adapter:                          # only for codetree delegations that need it
    include: ["src/**/*.py"]        # fnmatch globs; replaces the default extension filter
    exclude: ["*/generated/*"]      # fnmatch globs; added to the built-in skips
    depth: 2                        # 1 = chapter per group; 2 = per subdir (default)
  ```

- Write `corpora/<name>/v<N>/tools/adapter.py` implementing
  `scan(cfg: CorpusConfig, root: Path) -> Corpus`. A delegation is four
  lines — markdown course:

  ```python
  from tools.lingua.sources import markdown

  def scan(cfg, root):
      return markdown.scan(cfg, root)
  ```

  or code repo:

  ```python
  from tools.lingua.sources import codetree

  def scan(cfg, root):
      return codetree.scan(cfg, root)
  ```

  A fresh adapter:
  - Reuse the shared helpers above instead of re-implementing extraction.
  - Read name/title/urls/groups from `cfg`; keep only layout knowledge in
    the adapter. stdlib + pyyaml only; deterministic; no network; never
    write anything. Adapters are register-agnostic — the pipeline stamps
    the register onto the scan result.
  - `content_hash` must be a stable 12-hex digest of the chapter's source
    content — it pins every anchor's `curated_against`.
  - Group ids `lexicon`, `phrasebook`, `relations`, `concept-relations`,
    `chat`, `api`, `assets` are reserved (they would shadow viewer routes or
    generated pages) — the build rejects them.
  - In Build-together mode, write in logical blocks (group discovery →
    chapter loop → hashing), explaining each and confirming before the
    next — checkpoints, not a line-by-line quiz.

- Iterate `uv run python -m tools.lingua status` until the scan succeeds
  and the chapter list looks right (ids like `<name>/v<N>/<group>/<NN>`,
  groups, titles, kinds). Spot-check with
  `uv run python -m tools.lingua extract <id>` — the bundle should show the
  Translation requirements section and one Methodology section per selected
  dimension.

## 6. Build and finish

1. `uv run python -m tools.lingua` — full build; then review the summary and
   a couple of pages under `corpora/<name>/v<N>/pages/`.
2. Report: chapters per group, chapter kinds, per-dimension states (new
   registers start with every tracked state `none` — that is normal), and
   each mode's status (implemented modes are active; custom modes are
   recorded — not yet implemented).
3. Hand over ownership — nothing gets committed; everything under
   `corpora/` is gitignored and lives only on this machine:
   - The adapter is the learner's: edit
     `corpora/<name>/v<N>/tools/adapter.py`, rebuild with
     `uv run python -m tools.lingua`.
   - Update the material: `git -C corpora/<name>/source pull`, then rebuild
     — changed chapters flag their anchors stale per dimension, in every
     register.
   - Extract: `/translate <name>/v<N>` authors the register's lexicon,
     phrasebook, and concept relations per its translation requirements;
     `data/` is the register's accumulated value.
   - Iterate: `/mount` the same corpus again to create `v<N+1>` — a fresh
     retelling with different translation requirements; older registers
     stay browsable.
   - Browse: `cd web && npm run dev`.
   - Backups of `corpora/` are the learner's job — each register's `data/`
     especially.
4. Do whatever the form's **Next** answer chose, with explicit targets.

## Guardrails

- Never modify anything under `corpora/*/source/` — corpus material is
  read-only (and may be someone else's licensed work).
- Never hand-write files under `pages/` (generated) or `data/` (extraction
  flows through `/translate` and `uv run python -m tools.lingua set`).
- The adapter must not touch the network or mutate state.
- The form and the plan gate are mandatory.
- Registers are append-only: creating `v<N+1>` never edits an older
  register's translation.yaml, adapter, or data/.
- Never share or copy `data/` between registers — each retelling is
  extracted from scratch against its own requirements; that's the point.
- One `source/` per corpus; never a second checkout under a register.
- Don't fight the model: if material genuinely doesn't fit the
  group/chapter shape, say so and discuss options with the user instead of
  forcing a bad mapping.
