"""Write corpora/.manifest.json (version 6) and delete outputs for removed chapters.

The manifest is a clean index: full lexicon/phrasebook/relations payloads
live only in the per-register data files, whose corpora-relative paths the
manifest declares under corpora[].data — the viewer and the learning agent
read those files directly. Manifest keys are a lockstep contract shared with
web/lib/content.ts and .claude/agents/*.md — change them together or not at
all.
"""

import json
from pathlib import Path

from . import dimensions
from .render import dimension_page_relpath, index_relpath
from .status import RegisterBundle

VERSION = 6


def _corpus_entry(bundle: RegisterBundle) -> dict:
    corpus = bundle.corpus
    reg_states = bundle.register_states()
    data = {
        slug: {
            "state": reg_states[slug],
            "path": f"{corpus.name}/{corpus.register}/data/"
                    f"{dimensions.REGISTRY[slug].DATA_FILENAME}",
        }
        for slug in bundle.tracked_modes
    }
    pages = {"index": index_relpath(corpus)}
    for slug in bundle.tracked_modes:
        pages[slug] = dimension_page_relpath(corpus, slug)
    return {
        "name": corpus.name,
        "register": corpus.register,
        "label": corpus.label,
        "title": corpus.title,
        "checkout": corpus.checkout,
        "urls": corpus.urls,
        "source_kind": corpus.source_kind,
        "modes": bundle.tracked_modes,
        "recorded_modes": bundle.recorded_modes,
        "groups": [{"id": g.id, "label": g.label} for g in corpus.groups],
        "data": data,
        "pages": pages,
        "totals": bundle.totals(),
    }


def _chapter_entry(bundle: RegisterBundle, chapter) -> dict:
    corpus = bundle.corpus
    entry = {
        "id": chapter.id,
        "corpus": chapter.corpus,
        "register": chapter.register,
        "group": chapter.group,
        "number": chapter.number,
        "slug": chapter.slug,
        "title": chapter.title,
        "kind": chapter.kind,
        "content_hash": chapter.content_hash,
        "page": chapter.page_relpath,
        "source_paths": [
            p.relative_to(corpus.root).as_posix() for p in chapter.unit_paths
        ],
        "states": bundle.chapter_states(chapter),
    }
    local = chapter.local_id
    if "lexicon" in bundle.tracked_modes:
        lexmod = dimensions.REGISTRY["lexicon"]
        lexicon = bundle.data["lexicon"]
        entry["terms_defined"] = lexmod.terms_defined(lexicon, local)
        entry["terms_mentioned"] = lexmod.terms_mentioned(lexicon, local)
    if "phrasebook" in bundle.tracked_modes:
        entry["phrases"] = sorted(
            dimensions.REGISTRY["phrasebook"].entries_for_chapter(
                bundle.data["phrasebook"], local))
    if "concept-relations" in bundle.tracked_modes:
        entry["edges"] = dimensions.REGISTRY["concept-relations"].count(
            dimensions.REGISTRY["concept-relations"].entries_for_chapter(
                bundle.data["concept-relations"], local))
    return entry


def write_manifest_and_clean(
    corpora_dir: Path, bundles: list[RegisterBundle]
) -> list[Path]:
    manifest = {
        "version": VERSION,
        "corpora": [_corpus_entry(b) for b in bundles],
        "chapters": [
            _chapter_entry(b, c) for b in bundles for c in b.corpus.chapters
        ],
    }
    (corpora_dir / ".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # Sweep each register's pages/ tree only — never source/, data/, tools/,
    # corpus.yaml, or another register's pages. Expected set covers ALL of the
    # register's chapters (not just an --only subset) so partial renders never
    # sweep pages that weren't regenerated this run.
    removed = []
    for bundle in bundles:
        corpus = bundle.corpus
        pages_dir = corpora_dir / corpus.name / corpus.register / "pages"
        if not pages_dir.is_dir():
            continue
        expected = {corpora_dir / c.page_relpath for c in corpus.chapters}
        expected.add(corpora_dir / index_relpath(corpus))
        expected.update(
            corpora_dir / dimension_page_relpath(corpus, slug)
            for slug in bundle.tracked_modes
        )
        for page in sorted(pages_dir.rglob("*.md")):
            if page not in expected:
                page.unlink()
                removed.append(page)
        # Prune emptied group directories bottom-up.
        for d in sorted((p for p in pages_dir.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
    return removed
