"""Per-chapter, per-dimension extraction states and the status report.

States are computed, never stored: each dimension derives ok | stale | none
for a chapter from the anchors referencing it (plus dimension-specific drift
rules like dangling relation endpoints). A mode that isn't in the register's
translation.yaml is not tracked at all — coverage pressure only where the
learner asked for it.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import dimensions
from .model import Chapter, Corpus

STATES = ("ok", "stale", "none")

# Dimension slug -> the noun its entries are counted as in totals.
COUNT_KEYS = {
    "lexicon": "terms",
    "phrasebook": "phrases",
    "concept-relations": "relations",
}

MOUNT_HINT = (
    "no corpora mounted under corpora/ — run /mount <repo-url> in Claude Code "
    "to mount one"
)


@dataclass
class RegisterBundle:
    """One (corpus, register) with its loaded data files and derived states."""

    corpus: Corpus
    data_dir: Path
    data: dict[str, dict]  # dimension slug -> loaded data
    warnings: list[str] = field(default_factory=list)

    @property
    def tracked_modes(self) -> list[str]:
        """Active modes with shipped machinery, in registry order."""
        return [m for m in dimensions.REGISTRY if m in self.corpus.modes]

    @property
    def recorded_modes(self) -> list[str]:
        return [m for m in self.corpus.modes if m not in dimensions.REGISTRY]

    def chapter_states(self, chapter: Chapter) -> dict[str, str]:
        return {
            slug: dimensions.REGISTRY[slug].chapter_state(
                self.data[slug], chapter, self.data
            )
            for slug in self.tracked_modes
        }

    def register_states(self) -> dict[str, str]:
        """Worst-of-chapters per dimension: stale beats none beats ok."""
        out = {}
        for slug in self.tracked_modes:
            states = [self.chapter_states(c)[slug] for c in self.corpus.chapters]
            if "stale" in states:
                out[slug] = "stale"
            elif "none" in states or not states:
                out[slug] = "none"
            else:
                out[slug] = "ok"
        return out

    def totals(self) -> dict[str, int]:
        return {
            COUNT_KEYS[slug]: dimensions.REGISTRY[slug].count(self.data[slug])
            for slug in self.tracked_modes
        }

    def state_counters(self) -> dict[str, Counter]:
        counters = {slug: Counter() for slug in self.tracked_modes}
        for chapter in self.corpus.chapters:
            for slug, state in self.chapter_states(chapter).items():
                counters[slug][state] += 1
        return counters


def build_bundle(corpus: Corpus, data_dir: Path) -> RegisterBundle:
    """Load every implemented dimension's data file for one register and
    collect its data-level warnings. Raises LinguaDataError on unusable files."""
    data = {}
    for slug, module in dimensions.REGISTRY.items():
        data[slug] = module.load(data_dir / module.DATA_FILENAME)
    bundle = RegisterBundle(corpus=corpus, data_dir=data_dir, data=data)
    where_prefix = f"corpora/{corpus.name}/{corpus.register}/data"
    for slug in bundle.tracked_modes:
        module = dimensions.REGISTRY[slug]
        bundle.warnings += module.warnings(
            data[slug], corpus, data, f"{where_prefix}/{module.DATA_FILENAME}"
        )
    return bundle


def state_summary(counts: Counter) -> str:
    """'40 ok, 2 stale' — omits zero-count states."""
    return ", ".join(f"{counts[s]} {s}" for s in STATES if counts[s])


def all_ok(bundles: list[RegisterBundle]) -> bool:
    return all(
        state == "ok"
        for bundle in bundles
        for chapter in bundle.corpus.chapters
        for state in bundle.chapter_states(chapter).values()
    )


def status_json(bundles: list[RegisterBundle]) -> dict:
    """The machine-readable status contract (shared with web/ and the
    authoring agents — change in lockstep or not at all)."""
    totals: dict[str, Counter] = {}
    chapters = []
    for bundle in bundles:
        for slug, counter in bundle.state_counters().items():
            totals.setdefault(slug, Counter()).update(counter)
        lexicon = bundle.data.get("lexicon", {})
        lexmod = dimensions.REGISTRY["lexicon"]
        for c in bundle.corpus.chapters:
            entry = {
                "id": c.id, "corpus": c.corpus, "register": c.register,
                "group": c.group, "number": c.number, "title": c.title,
                "kind": c.kind, "content_hash": c.content_hash,
                "page": c.page_relpath,
                "states": bundle.chapter_states(c),
            }
            if "lexicon" in bundle.tracked_modes:
                entry["terms_defined"] = len(lexmod.terms_defined(lexicon, c.local_id))
                entry["terms_mentioned"] = len(
                    lexmod.terms_mentioned(lexicon, c.local_id))
            if "phrasebook" in bundle.tracked_modes:
                entry["phrases"] = len(
                    dimensions.REGISTRY["phrasebook"].entries_for_chapter(
                        bundle.data["phrasebook"], c.local_id))
            if "concept-relations" in bundle.tracked_modes:
                entry["edges"] = dimensions.REGISTRY["concept-relations"].count(
                    dimensions.REGISTRY["concept-relations"].entries_for_chapter(
                        bundle.data["concept-relations"], c.local_id))
            chapters.append(entry)
    return {
        "corpora": [
            {
                "name": b.corpus.name, "register": b.corpus.register,
                "label": b.corpus.label, "checkout": b.corpus.checkout,
                "modes": b.corpus.modes, "source_kind": b.corpus.source_kind,
                "totals": b.totals(),
            }
            for b in bundles
        ],
        "chapters": chapters,
        "totals": {slug: dict(counter) for slug, counter in totals.items()},
    }


def print_status(bundles: list[RegisterBundle], as_json: bool) -> int:
    if as_json:
        print(json.dumps(status_json(bundles), indent=2))
        return 0
    if not bundles:
        print(MOUNT_HINT)
        return 0
    chapters = [(b, c) for b in bundles for c in b.corpus.chapters]
    id_w = max(32, *(len(c.id) + 1 for _, c in chapters)) if chapters else 32
    columns = list(dimensions.REGISTRY)
    print(f"{'id':<{id_w}} " + " ".join(f"{s:<18}" for s in columns))
    for bundle, chapter in chapters:
        states = bundle.chapter_states(chapter)
        print(f"{chapter.id:<{id_w}} "
              + " ".join(f"{states.get(s, '-'):<18}" for s in columns))
    parts = []
    combined: dict[str, Counter] = {}
    for bundle in bundles:
        for slug, counter in bundle.state_counters().items():
            combined.setdefault(slug, Counter()).update(counter)
    for slug in columns:
        if slug in combined:
            parts.append(f"{slug} {state_summary(combined[slug]) or '-'}")
    print(f"\n{len(chapters)} chapters | " + " | ".join(parts))
    return 0
