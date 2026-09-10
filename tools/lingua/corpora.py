"""Discover mounted corpora and load their adapters.

A corpus is a directory in the reference room of the development environment
(devenv/reference/ — gitignored in full, so corpora live only on the learner's
machine). Corpus-level facts live at the top; each
register ("v1", "v2", ...) is a distinct retelling of the same material:

    corpus.yaml            corpus config (title, urls, origin)
    source/                checkout of the material — shared by all registers
    derived/<recipe>/      generated material — a Markdown tree produced from
                           source/ by `ch doc`, git-committed so it hashes and
                           versions exactly like a checkout
    v1/translation.yaml    the register's translation requirements
    v1/tools/adapter.py    adapter exposing scan(cfg, root) -> Corpus
    v1/data/               extracted linguistic structure (lexicon.yaml,
                           phrasebook.yaml, relations.yaml — machine-owned)
    v1/pages/              generated pages

The directory name is the corpus id. Corpora are mounted interactively via
the /mount Claude Code skill, which gathers the translation requirements and
authors each register's adapter together with the learner; re-running /mount
on a mounted corpus creates the next register.
"""

import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from . import translation
from .model import CHAPTER_KINDS, RESERVED_GROUP_IDS, Corpus, Group
from .devenv import REFERENCE_LABEL

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REGISTER_RE = re.compile(r"^v[1-9][0-9]*$")
CORPUS_KEYS = {"title", "origin", "urls"}


class CorpusError(Exception):
    pass


@dataclass(frozen=True)
class CorpusConfig:
    name: str  # directory name in the reference room — the corpus id
    register: str  # register directory name — "v1"
    corpus_dir: Path  # <reference>/<name>
    dir: Path  # <reference>/<name>/<register>
    title: str
    urls: dict[str, str]
    origin: str | None
    label: str | None  # register label from translation.yaml
    modes: list[str]  # translation mode slugs
    translation_notes: str | None
    groups: list[Group] | None  # None -> adapter default
    # Which tree under corpus_dir this register scans: None/"source" is the
    # checkout, "derived/<recipe>" a generated tree. One material per register.
    material: str | None = None
    adapter_options: dict = field(default_factory=dict)  # adapter: knobs, passed through

    @property
    def source_dir(self) -> Path:
        """The tree the adapter scans. A register elects it with `material:`;
        the adapter contract stays single-rooted either way."""
        return self.corpus_dir / (self.material or "source")

    @property
    def data_dir(self) -> Path:
        return self.dir / "data"

    @property
    def pages_dir(self) -> Path:
        return self.dir / "pages"

    @property
    def adapter_path(self) -> Path:
        return self.dir / "tools" / "adapter.py"


def _load_corpus_yaml(corpus_dir: Path) -> tuple[dict, list[str]]:
    """Load and validate devenv/reference/<name>/corpus.yaml (corpus-level config).
    Returns ({title, urls, origin}, warnings); raises CorpusError on anything
    unusable."""
    name = corpus_dir.name
    path = corpus_dir / "corpus.yaml"
    where = f"{REFERENCE_LABEL}/{name}/corpus.yaml"
    if not NAME_RE.fullmatch(name):
        raise CorpusError(f"corpus directory name {name!r} must match {NAME_RE.pattern}")
    if REGISTER_RE.fullmatch(name):
        raise CorpusError(
            f"corpus directory name {name!r} is reserved for register dirs (v1, v2, ...)"
        )
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise CorpusError(f"{where}: {exc}") from exc
    if not isinstance(data, dict):
        raise CorpusError(f"{where}: expected a mapping")

    warnings = []
    for key in data:
        if key == "groups":
            warnings.append(
                f"{where}: 'groups' moved to v<N>/translation.yaml — ignored here"
            )
        elif key not in CORPUS_KEYS:
            warnings.append(f"{where}: unknown key {key!r} ignored")

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise CorpusError(f"{where}: 'title' is required and must be a non-empty string")

    urls = data.get("urls") or {}
    if not isinstance(urls, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in urls.items()
    ):
        raise CorpusError(f"{where}: 'urls' must map string keys to string URLs")

    origin = data.get("origin")
    if origin is not None and not isinstance(origin, str):
        raise CorpusError(f"{where}: 'origin' must be a string")

    return {"title": title.strip(), "urls": dict(urls), "origin": origin}, warnings


def _validate_material(cfg: CorpusConfig, where: str) -> None:
    """A derived material must exist, carry its recipe, and stay in the corpus.

    `source` is exempt from every check here: /ch:mount symlinks it to an
    absolute path for a local folder, and a missing checkout is the adapter's
    ScanError to raise, with better words than this function has.
    """
    if cfg.material is None or cfg.material == "source":
        return
    resolved = cfg.source_dir.resolve()
    if not resolved.is_relative_to(cfg.corpus_dir.resolve()):
        raise CorpusError(
            f"{where}: material {cfg.material!r} resolves to {resolved} — "
            f"outside devenv/reference/{cfg.name}/. A derived tree is generated in "
            f"place; it is never a symlink elsewhere"
        )
    if not cfg.source_dir.is_dir():
        raise CorpusError(
            f"{where}: material {cfg.material!r} not found — generate it with "
            f"`./ch doc --stage {cfg.name} --from <recipe.json>` then "
            f"`./ch doc --promote {cfg.name}/{cfg.material.split('/')[-1]}`"
        )
    if not (cfg.source_dir / ".chiron" / "recipe.yaml").is_file():
        raise CorpusError(
            f"{where}: {cfg.material}/ has no .chiron/recipe.yaml — a derived "
            f"tree records the recipe that generated it, so it can be "
            f"regenerated and its provenance read; re-promote it"
        )


def load_config(corpus_dir: Path, register_dir: Path) -> tuple[CorpusConfig, list[str]]:
    """Load one (corpus, register) pair: corpus.yaml + translation.yaml."""
    corpus, warnings = _load_corpus_yaml(corpus_dir)
    where = f"{REFERENCE_LABEL}/{corpus_dir.name}/{register_dir.name}/translation.yaml"
    try:
        tcfg, tw = translation.load_translation(register_dir, where)
    except translation.TranslationError as exc:
        raise CorpusError(str(exc)) from exc
    warnings += tw
    cfg = CorpusConfig(
        name=corpus_dir.name, register=register_dir.name,
        corpus_dir=corpus_dir, dir=register_dir,
        title=corpus["title"], urls=corpus["urls"], origin=corpus["origin"],
        label=tcfg.label, modes=tcfg.modes,
        translation_notes=tcfg.notes, groups=tcfg.groups,
        material=tcfg.material, adapter_options=tcfg.adapter_options,
    )
    _validate_material(cfg, where)
    return cfg, warnings


def _register_dirs(corpus_dir: Path) -> list[Path]:
    return sorted(
        (p for p in corpus_dir.iterdir() if p.is_dir() and REGISTER_RE.fullmatch(p.name)),
        key=lambda p: int(p.name[1:]),
    )


def discover(reference_dir: Path) -> tuple[list[CorpusConfig], list[str]]:
    """Scan <reference>/*/v*/. Returns (configs, warnings); incomplete corpora and
    registers are skipped with a warning."""
    configs: list[CorpusConfig] = []
    warnings: list[str] = []
    if not reference_dir.is_dir():
        return configs, warnings
    for corpus_dir in sorted(p for p in reference_dir.iterdir() if p.is_dir()):
        name = corpus_dir.name
        if not (corpus_dir / "corpus.yaml").exists():
            warnings.append(
                f"{REFERENCE_LABEL}/{name}/ has no corpus.yaml — skipped "
                f"(unfinished mount? run /ch:mount to complete it)"
            )
            continue
        if (corpus_dir / "tools" / "adapter.py").exists() or any(
            (corpus_dir / d).is_dir() for d in ("notes", "pages")
        ):
            warnings.append(
                f"{REFERENCE_LABEL}/{name}/ has pre-versioned flat-layout artifacts "
                f"(tools/, notes/ or pages/ at the corpus level) — re-mount with "
                f"/mount; registers live under devenv/reference/{name}/v<N>/"
            )
        register_dirs = _register_dirs(corpus_dir)
        if not register_dirs:
            warnings.append(
                f"{REFERENCE_LABEL}/{name}/ has no registers — run /ch:mount to create v1"
            )
            continue
        for register_dir in register_dirs:
            if not (register_dir / "translation.yaml").exists():
                warnings.append(
                    f"{REFERENCE_LABEL}/{name}/{register_dir.name}/ has no translation.yaml — "
                    f"skipped (unfinished mount? run /ch:mount to complete it)"
                )
                continue
            cfg, w = load_config(corpus_dir, register_dir)
            configs.append(cfg)
            warnings += w
    return configs, warnings


def load_adapter(cfg: CorpusConfig) -> Callable[[CorpusConfig, Path], Corpus]:
    """Import devenv/reference/<name>/<vN>/tools/adapter.py and return its scan()."""
    where = f"{REFERENCE_LABEL}/{cfg.name}/{cfg.register}/tools/adapter.py"
    if not cfg.adapter_path.exists():
        raise CorpusError(f"{where} not found — run /ch:mount to build the register's adapter")
    spec = importlib.util.spec_from_file_location(
        f"chiron_corpus_{cfg.name.replace('-', '_')}_{cfg.register}_adapter",
        cfg.adapter_path,
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise CorpusError(f"{where}: import failed: {exc}") from exc
    scan = getattr(module, "scan", None)
    if not callable(scan):
        raise CorpusError(f"{where}: must define scan(cfg, root) -> Corpus")
    return scan


def _validate_scan(cfg: CorpusConfig, corpus: Corpus) -> None:
    """Reject adapter output that would break routes or curation keys."""
    where = f"{REFERENCE_LABEL}/{cfg.name}/{cfg.register}"
    reserved = sorted(g.id for g in corpus.groups if g.id in RESERVED_GROUP_IDS)
    if reserved:
        raise CorpusError(
            f"{where}: group id(s) {', '.join(reserved)} are reserved "
            f"(they would shadow viewer routes or generated pages)"
        )
    seen: set[str] = set()
    for chapter in corpus.chapters:
        if chapter.kind not in CHAPTER_KINDS:
            raise CorpusError(
                f"{where}: chapter {chapter.local_id} has kind {chapter.kind!r} "
                f"(expected one of {', '.join(CHAPTER_KINDS)})"
            )
        if not re.fullmatch(r"[0-9a-f]{12}", chapter.content_hash):
            raise CorpusError(
                f"{where}: chapter {chapter.local_id} content_hash must be a "
                f"12-hex digest, got {chapter.content_hash!r}"
            )
        if chapter.local_id in seen:
            raise CorpusError(f"{where}: duplicate chapter id {chapter.local_id}")
        seen.add(chapter.local_id)


def scan_corpus(cfg: CorpusConfig) -> Corpus:
    """Run the register's adapter and stamp the register metadata it doesn't
    know about — the adapter contract stays register-agnostic."""
    corpus = load_adapter(cfg)(cfg, cfg.source_dir)
    corpus.register = cfg.register
    corpus.label = cfg.label
    corpus.modes = list(cfg.modes)
    corpus.translation_notes = cfg.translation_notes
    for chapter in corpus.chapters:
        chapter.register = cfg.register
    _validate_scan(cfg, corpus)
    return corpus
