"""Discover mounted corpora and load their adapters.

A corpus is a directory under corpora/ (gitignored in full — corpora live
only on the learner's machine). Corpus-level facts live at the top; each
register ("v1", "v2", ...) is a distinct retelling of the same material:

    corpus.yaml            corpus config (title, urls, origin)
    source/                checkout of the material — shared by all registers
    v1/translation.yaml    the register's translation requirements
    v1/tools/adapter.py    adapter exposing scan(cfg, root) -> Corpus
    v1/data/               curation (flows.yaml, facts.yaml)
    v1/notes/              generated pages

The directory name is the corpus id. Corpora are mounted interactively via
the /mount Claude Code skill, which gathers the translation requirements and
authors each register's adapter together with the learner; re-running /mount
on a mounted corpus creates the next register.
"""

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

from . import translation
from .model import Corpus, Group

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REGISTER_RE = re.compile(r"^v[1-9][0-9]*$")
CORPUS_KEYS = {"title", "origin", "urls"}


class CorpusError(Exception):
    pass


@dataclass(frozen=True)
class CorpusConfig:
    name: str  # directory name under corpora/ — the corpus id
    register: str  # register directory name — "v1"
    corpus_dir: Path  # corpora/<name>
    dir: Path  # corpora/<name>/<register>
    title: str
    urls: dict[str, str]
    origin: str | None
    label: str | None  # register label from translation.yaml
    modes: list[str]  # translation mode slugs
    translation_notes: str | None
    groups: list[Group] | None  # None -> adapter default

    @property
    def source_dir(self) -> Path:
        return self.corpus_dir / "source"

    @property
    def data_dir(self) -> Path:
        return self.dir / "data"

    @property
    def notes_dir(self) -> Path:
        return self.dir / "notes"

    @property
    def adapter_path(self) -> Path:
        return self.dir / "tools" / "adapter.py"


def _load_corpus_yaml(corpus_dir: Path) -> tuple[dict, list[str]]:
    """Load and validate corpora/<name>/corpus.yaml (corpus-level config).
    Returns ({title, urls, origin}, warnings); raises CorpusError on anything
    unusable."""
    name = corpus_dir.name
    path = corpus_dir / "corpus.yaml"
    where = f"corpora/{name}/corpus.yaml"
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


def load_config(corpus_dir: Path, register_dir: Path) -> tuple[CorpusConfig, list[str]]:
    """Load one (corpus, register) pair: corpus.yaml + translation.yaml."""
    corpus, warnings = _load_corpus_yaml(corpus_dir)
    where = f"corpora/{corpus_dir.name}/{register_dir.name}/translation.yaml"
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
    )
    return cfg, warnings


def _register_dirs(corpus_dir: Path) -> list[Path]:
    return sorted(
        (p for p in corpus_dir.iterdir() if p.is_dir() and REGISTER_RE.fullmatch(p.name)),
        key=lambda p: int(p.name[1:]),
    )


def discover(corpora_dir: Path) -> tuple[list[CorpusConfig], list[str]]:
    """Scan corpora/*/v*/. Returns (configs, warnings); incomplete corpora and
    registers are skipped with a warning."""
    configs: list[CorpusConfig] = []
    warnings: list[str] = []
    if not corpora_dir.is_dir():
        return configs, warnings
    for corpus_dir in sorted(p for p in corpora_dir.iterdir() if p.is_dir()):
        name = corpus_dir.name
        if not (corpus_dir / "corpus.yaml").exists():
            warnings.append(
                f"corpora/{name}/ has no corpus.yaml — skipped "
                f"(unfinished mount? run /mount to complete it)"
            )
            continue
        if (corpus_dir / "tools" / "adapter.py").exists() or (corpus_dir / "notes").is_dir():
            warnings.append(
                f"corpora/{name}/ has pre-versioned flat-layout artifacts "
                f"(tools/ or notes/ at the corpus level) — re-mount with /mount; "
                f"registers live under corpora/{name}/v<N>/"
            )
        register_dirs = _register_dirs(corpus_dir)
        if not register_dirs:
            warnings.append(
                f"corpora/{name}/ has no registers — run /mount to create v1"
            )
            continue
        for register_dir in register_dirs:
            if not (register_dir / "translation.yaml").exists():
                warnings.append(
                    f"corpora/{name}/{register_dir.name}/ has no translation.yaml — "
                    f"skipped (unfinished mount? run /mount to complete it)"
                )
                continue
            cfg, w = load_config(corpus_dir, register_dir)
            configs.append(cfg)
            warnings += w
    return configs, warnings


def load_adapter(cfg: CorpusConfig) -> Callable[[CorpusConfig, Path], Corpus]:
    """Import corpora/<name>/<vN>/tools/adapter.py and return its scan()."""
    where = f"corpora/{cfg.name}/{cfg.register}/tools/adapter.py"
    if not cfg.adapter_path.exists():
        raise CorpusError(f"{where} not found — run /mount to build the register's adapter")
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
    return corpus
