"""The development environment's two rooms, and the one place that knows them.

chiron is a development environment for prompting. You read a **reference**
corpus to construct an instruction in that repo's own working language, then
apply it in a **workspace** repo you actually edit. Those are two different
relationships to a checkout — one read-only and extracted-from, one written-to
— so they are two rooms, not one flat tree:

    chiron.yaml                 declares the layout (tracked, optional)
    devenv/                     the root — gitignored in full
      reference/<name>/         a mounted corpus; see corpora.py for its shape
      workspace/<name>/         a repo a refined prompt gets applied to

Before this module the root was a string built once in __main__ and hardcoded
another forty times in messages, so nothing could check that a directory under
it was in the right room. Here the layout is declared, validated, and confined:
`discover()` is only ever handed `reference`, so a checkout dropped anywhere
else is not silently half-mounted — `strays()` names it instead.

`REFERENCE_LABEL` is what error messages print. It is the default spelling, not
the resolved path: renaming a room in chiron.yaml leaves those strings stale
while behaviour stays correct. `./ch devenv` prints the real paths, which is
where to go when a message disagrees with the disk.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_NAME = "chiron.yaml"
DEFAULT_ROOT = "devenv"
DEFAULT_REFERENCE = "reference"
DEFAULT_WORKSPACE = "workspace"
ROOM_KEYS = {"root", "reference", "workspace"}
ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# The spelling every message uses. See the module docstring on why it is a
# constant rather than a property of the resolved Devenv.
REFERENCE_LABEL = f"{DEFAULT_ROOT}/{DEFAULT_REFERENCE}"
WORKSPACE_LABEL = f"{DEFAULT_ROOT}/{DEFAULT_WORKSPACE}"

LEGACY_ROOT = "corpora"
ROOT_ENV = "CHIRON_DEVENV"


class DevenvError(Exception):
    pass


@dataclass(frozen=True)
class Devenv:
    """One resolved development environment. Paths are absolute."""

    root: Path
    reference: Path
    workspace: Path
    config_path: Path | None  # None -> no chiron.yaml on disk, defaults used

    @property
    def rooms(self) -> tuple[Path, Path]:
        return (self.reference, self.workspace)

    def ensure(self) -> None:
        """Create both rooms. Idempotent, and cheap enough to run on every
        command — every later path is valid once it has."""
        for room in self.rooms:
            room.mkdir(parents=True, exist_ok=True)

    def strays(self) -> list[str]:
        """Entries directly under the root that are in neither room. Nothing
        scans them, so without this they would sit there looking mounted."""
        if not self.root.is_dir():
            return []
        names = {room.name for room in self.rooms}
        return sorted(
            p.name for p in self.root.iterdir()
            if p.name not in names and not p.name.startswith(".")
        )

    def count(self, room: Path) -> int:
        if not room.is_dir():
            return 0
        return sum(
            1 for p in room.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )


def injected(reference: Path) -> Devenv:
    """The environment implied by an injected reference room, for callers that
    bypass config resolution — the test suite, and anything embedding main().
    It reports what it was handed rather than pretending to have read config."""
    root = reference.parent
    return Devenv(root=root, reference=reference,
                  workspace=root / DEFAULT_WORKSPACE, config_path=None)


def _room(data: dict, key: str, default: str, where: str) -> str:
    """A room is one safe path segment inside the root — never absolute, never
    a traversal. Validated here so `root / room` cannot escape the root."""
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise DevenvError(f"{where}: devenv.{key} must be a non-empty string")
    value = value.strip()
    if not ROOM_RE.fullmatch(value):
        raise DevenvError(
            f"{where}: devenv.{key} is {value!r} — a room is one directory "
            f"name inside the devenv root, matching {ROOM_RE.pattern} "
            f"(not a path, not absolute, not '..')"
        )
    return value


def load(repo_root: Path, environ: dict | None = None) -> tuple[Devenv, list[str]]:
    """Resolve the development environment. Returns (devenv, warnings).

    A missing chiron.yaml is not an error — the defaults are the shipped
    layout, so a fresh clone works before anyone writes any config.
    """
    environ = os.environ if environ is None else environ
    warnings: list[str] = []
    path = repo_root / CONFIG_NAME
    config_path: Path | None = None
    data: dict = {}

    if path.is_file():
        config_path = path
        try:
            loaded = yaml.safe_load(path.read_text()) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise DevenvError(f"{CONFIG_NAME}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise DevenvError(f"{CONFIG_NAME}: expected a mapping")
        section = loaded.get("devenv", {})
        if section is None:
            section = {}
        if not isinstance(section, dict):
            raise DevenvError(f"{CONFIG_NAME}: 'devenv' must be a mapping")
        data = section
        for key in data:
            if key not in ROOM_KEYS:
                warnings.append(f"{CONFIG_NAME}: unknown key devenv.{key!r} ignored")

    override = (environ.get(ROOT_ENV) or "").strip()
    if override:
        root = Path(override).expanduser()
        if not root.is_absolute():
            root = (repo_root / root).resolve()
    else:
        raw = data.get("root", DEFAULT_ROOT)
        if not isinstance(raw, str) or not raw.strip():
            raise DevenvError(f"{CONFIG_NAME}: devenv.root must be a non-empty string")
        root = Path(raw.strip()).expanduser()
        if not root.is_absolute():
            root = repo_root / root

    where = CONFIG_NAME if config_path else "devenv defaults"
    reference = root / _room(data, "reference", DEFAULT_REFERENCE, where)
    workspace = root / _room(data, "workspace", DEFAULT_WORKSPACE, where)
    if reference == workspace:
        raise DevenvError(
            f"{where}: devenv.reference and devenv.workspace are both "
            f"{reference.name!r} — the two rooms must be distinct"
        )

    dv = Devenv(root=root, reference=reference, workspace=workspace,
                config_path=config_path)
    _check_legacy(repo_root, dv)
    return dv, warnings


def _check_legacy(repo_root: Path, dv: Devenv) -> None:
    """A half-migrated tree must not half-work. If the pre-devenv devenv/reference/
    still holds corpora and the reference room does not, stop and say the move."""
    legacy = repo_root / LEGACY_ROOT
    if not legacy.is_dir():
        return
    mounted = [p for p in legacy.iterdir() if p.is_dir()]
    if not mounted:
        return
    if dv.reference.is_dir() and any(
        p.is_dir() for p in dv.reference.iterdir()
    ):
        return
    names = " ".join(f"{LEGACY_ROOT}/{p.name}" for p in sorted(mounted, key=lambda p: p.name))
    raise DevenvError(
        f"{LEGACY_ROOT}/ still holds mounted corpora, but they now live in "
        f"{REFERENCE_LABEL}/. Move them, then re-run:\n"
        f"  mkdir -p {dv.reference} {dv.workspace}\n"
        f"  mv {names} {LEGACY_ROOT}/.manifest.json {dv.reference}/\n"
        f"  rmdir {LEGACY_ROOT}"
    )


def _display(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def print_devenv(dv: Devenv, repo_root: Path, warnings: list[str] | None = None) -> int:
    """`ch devenv` — the resolved layout, so the skills can read it rather than
    assume it. Writes nothing."""
    for warning in warnings or []:
        print(f"warning: {warning}")
    print(f"root        {dv.root}")
    print(f"config      {_display(dv.config_path, repo_root) if dv.config_path else f'(defaults — no {CONFIG_NAME})'}")
    for label, room in (("reference", dv.reference), ("workspace", dv.workspace)):
        count = dv.count(room)
        noun = "corpus" if label == "reference" else "repo"
        plural = "corpora" if label == "reference" else "repos"
        held = f"{count} {noun if count == 1 else plural}" if count else "(empty)"
        print(f"{label:<11} {_display(room, repo_root):<22} {held}")
    for stray in dv.strays():
        print(f"stray       {_display(dv.root / stray, repo_root):<22} "
              f"not a room — nothing scans it; move it into "
              f"{dv.reference.name}/ or {dv.workspace.name}/")
    return 0
