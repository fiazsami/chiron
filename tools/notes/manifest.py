"""Write corpora/.manifest.json and delete outputs for removed chapters."""

import json
from pathlib import Path

from .model import Corpus
from .render import svg_relpaths


def write_manifest_and_clean(corpora_dir: Path, corpora: list[Corpus]) -> list[Path]:
    manifest = {
        "version": 5,
        "corpora": [
            {
                "name": s.name,
                "register": s.register,
                "label": s.label,
                "title": s.title,
                "checkout": s.checkout,
                "urls": s.urls,
                "has_labs": s.has_labs,
                "modes": s.modes,
                "groups": [{"id": g.id, "label": g.label} for g in s.groups],
            }
            for s in corpora
        ],
        "chapters": [
            {
                "id": c.id,
                "corpus": c.corpus,
                "register": c.register,
                "group": c.group,
                "slug": c.slug,
                "title": c.short_title,
                "lab": c.lab_slug,
                "components": c.components,
                "content_hash": c.content_hash,
                "content": {"schematic": c.schematic_state, "facts": c.facts_state},
                "page": c.page_relpath,
                "svgs": svg_relpaths(c),
            }
            for s in corpora
            for c in s.chapters
        ],
    }
    (corpora_dir / ".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # Sweep each register's notes/ tree only — never source/, data/, tools/,
    # corpus.yaml, or another register's notes. Expected set covers ALL of the
    # register's chapters (not just an --only subset) so partial renders never
    # sweep pages that weren't regenerated this run.
    removed = []
    for corpus in corpora:
        notes_dir = corpora_dir / corpus.name / corpus.register / "notes"
        if not notes_dir.is_dir():
            continue
        expected = {corpora_dir / c.page_relpath for c in corpus.chapters}
        expected.update(
            corpora_dir / rel for c in corpus.chapters for rel in svg_relpaths(c)
        )
        expected.add(notes_dir / "README.md")
        for pattern in ("*.md", "*.svg"):
            for page in sorted(notes_dir.rglob(pattern)):
                if page not in expected:
                    page.unlink()
                    removed.append(page)
        # Prune emptied directories bottom-up (assets/, then group dirs).
        for d in sorted((p for p in notes_dir.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
    return removed
