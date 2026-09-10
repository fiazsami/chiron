"""Load and validate a register's translation.yaml.

translation.yaml records the translation requirements gathered by /mount for
one register of a corpus: which linguistic dimensions (modes) the retelling
extracts, an optional display label, free-text notes that steer the authoring
agents, which material tree the register scans, an optional groups override
for the adapter, and optional adapter knobs. Modes are extensible slugs:
"implemented" ones are dimensions shipped in tools/lingua/dimensions/ (each
bound to a methodology/<slug>.md plan); "recorded" ones are stored and
surfaced but have no extraction machinery yet.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import dimensions
from .model import Group

MODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GROUP_ID_RE = re.compile(r"^[a-z0-9-]+$")
# Which tree under corpora/<name>/ this register scans. "source" is the
# checkout; "derived/<recipe>" is a generated tree materialized by `ch doc`.
# Anchored and slug-shaped on both segments, so it can never escape the corpus.
MATERIAL_RE = re.compile(r"^(source|derived/[a-z0-9][a-z0-9-]*)$")
KNOWN_KEYS = {"label", "modes", "notes", "material", "groups", "adapter"}


class TranslationError(Exception):
    pass


@dataclass(frozen=True)
class TranslationConfig:
    label: str | None
    modes: list[str]
    notes: str | None
    groups: list[Group] | None  # None -> adapter default
    material: str | None = None  # None -> "source"; else "derived/<recipe>"
    adapter_options: dict = field(default_factory=dict)


def mode_status(slug: str) -> str:
    """"implemented" for dimensions with shipped machinery, else "recorded"."""
    return "implemented" if slug in dimensions.REGISTRY else "recorded"


def parse_groups(raw, where: str) -> list[Group]:
    """Validate a groups override ([{id, label}, ...])."""
    if not isinstance(raw, list) or not raw:
        raise TranslationError(f"{where}: 'groups' must be a non-empty list")
    groups = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("label"):
            raise TranslationError(f"{where}: each group needs 'id' and 'label'")
        if not GROUP_ID_RE.fullmatch(str(entry["id"])):
            raise TranslationError(
                f"{where}: group id {entry['id']!r} must match {GROUP_ID_RE.pattern}"
            )
        groups.append(Group(str(entry["id"]), str(entry["label"])))
    ids = [g.id for g in groups]
    if len(set(ids)) != len(ids):
        raise TranslationError(f"{where}: duplicate group ids")
    return groups


def load_translation(register_dir: Path, where: str) -> tuple[TranslationConfig, list[str]]:
    """Load and validate <register_dir>/translation.yaml. Returns the config
    and non-fatal warnings; raises TranslationError on anything unusable."""
    path = register_dir / "translation.yaml"
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise TranslationError(f"{where}: {exc}") from exc
    if not isinstance(data, dict):
        raise TranslationError(f"{where}: expected a mapping")

    warnings = [
        f"{where}: unknown key {key!r} ignored"
        for key in data
        if key not in KNOWN_KEYS
    ]

    modes = data.get("modes")
    if not isinstance(modes, list) or not modes or not all(
        isinstance(m, str) and MODE_RE.fullmatch(m) for m in modes
    ):
        raise TranslationError(
            f"{where}: 'modes' is required and must be a non-empty list of "
            f"slugs matching {MODE_RE.pattern}"
        )
    if len(set(modes)) != len(modes):
        raise TranslationError(f"{where}: duplicate modes")
    warnings += [
        f"{where}: custom mode {m!r} recorded — no extraction machinery for it yet"
        for m in modes
        if m not in dimensions.REGISTRY
    ]

    label = data.get("label")
    if label is not None and (not isinstance(label, str) or "\n" in label.strip()):
        raise TranslationError(f"{where}: 'label' must be a single-line string")

    notes = data.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise TranslationError(f"{where}: 'notes' must be a string")

    material = data.get("material")
    if material is not None and (
        not isinstance(material, str) or not MATERIAL_RE.fullmatch(material)
    ):
        raise TranslationError(
            f"{where}: 'material' must be 'source' or 'derived/<recipe>' "
            f"(recipe matching [a-z0-9][a-z0-9-]*), got {material!r}"
        )

    groups = None
    if data.get("groups") is not None:
        groups = parse_groups(data["groups"], where)

    adapter = data.get("adapter") or {}
    if not isinstance(adapter, dict) or not all(isinstance(k, str) for k in adapter):
        raise TranslationError(
            f"{where}: 'adapter' must be a mapping of option names (the "
            f"adapter validates the values)"
        )

    return TranslationConfig(
        label=label.strip() if label else None,
        modes=list(modes),
        notes=notes.strip() if notes and notes.strip() else None,
        groups=groups,
        material=material,
        adapter_options=dict(adapter),
    ), warnings
