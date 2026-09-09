"""Generic adapter for a corpus that is a folder (or git repo) of Markdown docs.

Expected layout: <root>/<group>/<doc>.md — one subdirectory per group. Docs
are ordered by an "NN-" filename prefix when present, else by sort position;
README/index files are skipped. Title comes from the first H1 (else the
filename stem), the description from frontmatter or the first paragraph, and
the first ```mermaid block feeds the fallback schematic.

A markdown-shaped corpus's tools/adapter.py just delegates here:

    from tools.notes.sources import markdown

    def scan(cfg, root):
        return markdown.scan(cfg, root)
"""

import hashlib
import re
from pathlib import Path

from tools.notes.corpora import CorpusConfig
from tools.notes.gittree import check_workdir, git_tree, sha256_file, source_version
from tools.notes.model import Chapter, Corpus, Group, ScanError
from tools.notes.sources import base

NUMBER_PREFIX_RE = re.compile(r"^(\d+[a-z]?)-")
SKIP_STEMS = {"readme", "index"}


def discover_groups(root: Path) -> list[Group]:
    """Default grouping: one group per top-level directory containing .md
    files, in sorted order, labeled by title-casing the directory name."""
    return [
        Group(p.name, p.name.replace("-", " ").title())
        for p in sorted(root.iterdir())
        if p.is_dir() and not p.name.startswith(".") and any(p.glob("*.md"))
    ]


def scan(cfg: CorpusConfig, root: Path) -> Corpus:
    if not root.is_dir():
        raise ScanError(f"corpus {cfg.name!r} source not found at {root}")
    groups = cfg.groups or discover_groups(root)
    if not groups:
        raise ScanError(
            f"corpus {cfg.name!r} has no group directories with .md files under {root}"
        )

    tree = git_tree(root)
    repo = cfg.urls.get("repo")
    chapters: list[Chapter] = []
    for group in groups:
        docs = [
            p for p in sorted((root / group.id).glob("*.md"))
            if p.stem.lower() not in SKIP_STEMS
        ]
        seen_numbers: set[str] = set()
        for position, doc_path in enumerate(docs, 1):
            slug = doc_path.stem
            m = NUMBER_PREFIX_RE.match(slug)
            number = m.group(1) if m else f"{position:02d}"
            if number in seen_numbers:
                raise ScanError(
                    f"corpus {cfg.name!r}: duplicate chapter number {number!r} in "
                    f"group {group.id!r} (doc {slug!r})"
                )
            seen_numbers.add(number)

            raw = doc_path.read_text()
            meta, body = base.parse_frontmatter(raw)
            doc_title = base.h1_title(body, slug)
            description = str(meta.get("description", "")) or base.first_paragraph(body)
            rel = doc_path.relative_to(root).as_posix()

            chapter = Chapter(
                corpus=cfg.name,
                group=group.id,
                group_label=group.label,
                number=number,
                slug=slug,
                title=doc_title,
                short_title=doc_title,
                description=description,
                doc_path=doc_path,
                # Branch name is a guess; corpora on a non-"main" default
                # branch should set urls.repo to a base that includes it.
                doc_source_url=f"{repo}/blob/main/{rel}" if repo else None,
                doc_hash=(tree or {}).get(rel) or sha256_file(doc_path),
                mermaid=base.first_mermaid(body),
            )
            chapter.detected_components = base.fingerprint_text(
                f"{chapter.title} {chapter.description}"
            )
            chapter.content_hash = hashlib.sha256(
                chapter.doc_hash.encode()
            ).hexdigest()[:12]
            chapters.append(chapter)

    checkout = source_version(root)
    if checkout == "unknown":  # plain folder: derive a digest from the content
        checkout = hashlib.sha256(
            "".join(c.content_hash for c in chapters).encode()
        ).hexdigest()[:7]

    return Corpus(
        name=cfg.name,
        title=cfg.title,
        root=root,
        checkout=checkout,
        urls=cfg.urls,
        groups=groups,
        chapters=chapters,
        warnings=check_workdir(root, cfg.name) if tree is not None else [],
    )
