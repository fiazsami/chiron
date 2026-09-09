"""Load and validate a register's translation.yaml.

translation.yaml records the translation requirements gathered by /mount for
one register of a corpus: which modes the retelling uses, an optional display
label, free-text notes that steer the authoring agents, and an optional groups
override for the adapter. Modes are extensible slugs: "implemented" ones map
onto shipped machinery, "recorded" ones are stored and surfaced but have no
renderer yet.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .model import Group

MODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GROUP_ID_RE = re.compile(r"^[a-z0-9-]+$")
KNOWN_KEYS = {"label", "modes", "notes", "groups"}

KNOWN_MODES = {
    "condense-text": "implemented",  # key facts machinery (--set-facts / facts.yaml)
    "redraw-svg": "implemented",  # curated flow lanes (flows.yaml + svgflow)
    "design-patterns": "recorded",  # no renderer yet
}


class TranslationError(Exception):
    pass


@dataclass(frozen=True)
class TranslationConfig:
    label: str | None
    modes: list[str]
    notes: str | None
    groups: list[Group] | None  # None -> adapter default


def mode_status(slug: str) -> str:
    """"implemented" for modes with shipped machinery, else "recorded"."""
    return KNOWN_MODES.get(slug, "recorded")


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
        f"{where}: custom mode {m!r} recorded — no renderer for it yet"
        for m in modes
        if m not in KNOWN_MODES
    ]

    label = data.get("label")
    if label is not None and (not isinstance(label, str) or "\n" in label.strip()):
        raise TranslationError(f"{where}: 'label' must be a single-line string")

    notes = data.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise TranslationError(f"{where}: 'notes' must be a string")

    groups = None
    if data.get("groups") is not None:
        groups = parse_groups(data["groups"], where)

    return TranslationConfig(
        label=label.strip() if label else None,
        modes=list(modes),
        notes=notes.strip() if notes and notes.strip() else None,
        groups=groups,
    ), warnings
