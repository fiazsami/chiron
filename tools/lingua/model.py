"""Normalized data model shared by every corpus adapter.

Adapters (devenv/reference/<name>/<vN>/tools/adapter.py, usually delegating to a
building block under tools/lingua/sources/) walk their corpus's native layout
and return a Corpus whose Chapters all have this shape; everything downstream
(extraction, curation, rendering, manifest, web) consumes only these records
and never needs to know how a particular corpus is structured.
"""

from dataclasses import dataclass, field
from pathlib import Path


class ScanError(Exception):
    pass


# Group ids that would shadow the viewer's static routes or generated pages.
RESERVED_GROUP_IDS = {
    "lexicon", "phrasebook", "relations", "concept-relations",
    "chat", "api", "assets",
}

CHAPTER_KINDS = ("doc", "code")


@dataclass(frozen=True)
class Group:
    """An ordered section within a corpus."""

    id: str  # "foundations"
    label: str  # "Foundations"


@dataclass
class Chapter:
    corpus: str  # corpus name, e.g. "fewshot-works-academy"
    group: str  # group id within the corpus
    group_label: str
    number: str  # ordering token within the group ("02", "02b")
    slug: str  # page filename stem, unique within (corpus, group)
    title: str
    description: str
    kind: str  # "doc" (one document) | "code" (a coherent code unit)
    # Ordered files constituting the chapter, relative-resolvable under the
    # corpus source root. A doc chapter has exactly one; a code chapter has
    # every included file of its unit. Anchor quotes are verified against
    # these files.
    unit_paths: list[Path]
    # The unit's entry point: the doc itself, or a code unit's README /
    # __init__ / entry file. None when nothing stands out.
    primary_path: Path | None = None
    source_url: str | None = None  # where the unit lives upstream, if known
    content_hash: str = ""  # 12-hex digest; pins every anchor's curated_against
    # Register dir name ("v1"); stamped by corpora.scan_corpus, never by
    # adapters — the adapter contract stays register-agnostic.
    register: str = ""

    @property
    def id(self) -> str:
        """Canonical chapter id, unique across corpora and registers."""
        return f"{self.corpus}/{self.register}/{self.group}/{self.number}"

    @property
    def local_id(self) -> str:
        """Register-relative id — the key used in that register's data files
        and anchors (data/ is per-register, so no version segment is needed)."""
        return f"{self.group}/{self.number}"

    @property
    def page_relpath(self) -> str:
        """Page path relative to the reference room."""
        return f"{self.corpus}/{self.register}/pages/{self.group}/{self.slug}.md"


@dataclass
class Corpus:
    name: str  # corpus directory name under the reference room
    title: str  # display title from corpus.yaml
    root: Path  # <reference>/<name>/source — shared by all registers
    checkout: str  # git short SHA of source/ (or a content digest for plain folders)
    urls: dict[str, str]  # {"site": ..., "repo": ...}
    groups: list[Group]  # ordered; drives index/README section order
    chapters: list[Chapter]
    source_kind: str = ""  # "markdown" | "code" | "custom"; set by the adapter
    # "<tool> · <recipe>" when this material was generated rather than written.
    # Set by the adapter, which is the only layer that reads the recipe. It is
    # not in the manifest: the viewer treats generated Markdown as Markdown.
    generated_by: str | None = None
    warnings: list[str] = field(default_factory=list)
    # Register metadata; stamped by corpora.scan_corpus, never by adapters.
    register: str = ""  # "v1"
    label: str | None = None  # one-line description of this retelling
    modes: list[str] = field(default_factory=list)  # translation mode slugs
    translation_notes: str | None = None  # free-text requirements for authors

    @property
    def group_ids(self) -> list[str]:
        return [g.id for g in self.groups]

    def chapter_by_local_id(self, local_id: str) -> Chapter | None:
        for chapter in self.chapters:
            if chapter.local_id == local_id:
                return chapter
        return None
