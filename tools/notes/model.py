"""Normalized data model shared by every corpus adapter.

Adapters under tools/notes/sources/ walk their corpus's native layout and
return a Corpus whose Chapters all have this shape; everything downstream
(curation, rendering, manifest, web) consumes only these records and never
needs to know how a particular corpus is structured.
"""

from dataclasses import dataclass, field
from pathlib import Path


class ScanError(Exception):
    pass


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
    short_title: str
    description: str
    doc_path: Path
    # Register dir name ("v1"); stamped by corpora.scan_corpus, never by
    # adapters — the adapter contract stays register-agnostic.
    register: str = ""
    # Links rendered under "Sources"; any may be absent for a given corpus.
    doc_url: str | None = None  # published chapter page
    doc_source_url: str | None = None  # chapter source file
    lab_source_url: str | None = None
    lab_path: Path | None = None
    lab_slug: str | None = None
    time_cost: str | None = None
    components: list[str] = field(default_factory=list)
    detected_components: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    lab_deps: list[str] = field(default_factory=list)
    mermaid: str | None = None
    readme_flow: str | None = None
    doc_hash: str = ""
    lab_hash: str | None = None
    content_hash: str = ""
    flow: dict | None = None
    fallback_flow: dict | None = None
    schematic_state: str = "none"  # ok | stale | fallback | none
    facts: dict | None = None
    facts_state: str = "none"  # ok | stale | none

    @property
    def id(self) -> str:
        """Canonical chapter id, unique across corpora and registers."""
        return f"{self.corpus}/{self.register}/{self.group}/{self.number}"

    @property
    def local_id(self) -> str:
        """Register-relative id — the key used in that register's curation
        files (data/ is per-register, so no version segment is needed)."""
        return f"{self.group}/{self.number}"

    @property
    def page_relpath(self) -> str:
        """Page path relative to the corpora/ root."""
        return f"{self.corpus}/{self.register}/notes/{self.group}/{self.slug}.md"

    @property
    def concept_only(self) -> bool:
        return self.lab_path is None


@dataclass
class Corpus:
    name: str  # corpus directory name under corpora/
    title: str  # display title from corpus.yaml
    root: Path  # corpora/<name>/source — shared by all registers
    checkout: str  # git short SHA of source/ (or a content digest for plain folders)
    urls: dict[str, str]  # {"site": ..., "repo": ...}
    groups: list[Group]  # ordered; drives index/README section order
    chapters: list[Chapter]
    warnings: list[str] = field(default_factory=list)
    # Register metadata; stamped by corpora.scan_corpus, never by adapters.
    register: str = ""  # "v1"
    label: str | None = None  # one-line description of this retelling
    modes: list[str] = field(default_factory=list)  # translation mode slugs
    translation_notes: str | None = None  # free-text requirements for authors

    @property
    def group_ids(self) -> list[str]:
        return [g.id for g in self.groups]

    @property
    def has_labs(self) -> bool:
        return any(c.lab_path is not None for c in self.chapters)
