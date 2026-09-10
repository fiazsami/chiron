"""Generic adapter for an undocumented code repository.

Deterministic chaptering with zero per-repo code: one group per top-level
directory containing included files (loose top-level files form the "root"
group); within a group, each immediate subdirectory whose subtree has
included files is one chapter, and files directly in the group directory
cluster into a "<group>-files" chapter. No heuristics that can flap between
runs — the same tree always yields the same chapters, so anchors stay put.

Adapter knobs, via `adapter:` in the register's translation.yaml:

    adapter:
      include: ["src/**/*.py"]   # fnmatch globs; replaces the default
                                 #   source-extension filter when present
      exclude: ["*/generated/*"] # fnmatch globs; added to the built-in skips
      depth: 2                   # 1 = one chapter per group (whole subtree);
                                 #   2 = one chapter per immediate subdir (default)

A code-shaped corpus's tools/adapter.py just delegates here:

    from tools.lingua.sources import codetree

    def scan(cfg, root):
        return codetree.scan(cfg, root)
"""

import fnmatch
import hashlib
import re
from pathlib import Path

from tools.lingua.corpora import CorpusConfig
from tools.lingua.devenv import REFERENCE_LABEL
from tools.lingua.gittree import (
    SKIP_DIRS, check_workdir, git_tree, sha256_file, source_version,
)
from tools.lingua.model import Chapter, Corpus, Group, ScanError
from tools.lingua.sources import base

DEFAULT_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".kt",
    ".swift", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".scala", ".sh",
    ".sql", ".md", ".yaml", ".yml", ".toml", ".json", ".css",
}
EXCLUDE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "uv.lock",
    "poetry.lock", "Cargo.lock", "go.sum", ".env",
}
PRIMARY_STEMS = ("__init__", "index", "main", "mod", "lib")
SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _options(cfg: CorpusConfig) -> tuple[list[str], list[str], int]:
    opts = dict(cfg.adapter_options)
    where = f"{REFERENCE_LABEL}/{cfg.name}/{cfg.register}/translation.yaml adapter:"
    unknown = set(opts) - {"include", "exclude", "depth"}
    if unknown:
        raise ScanError(f"{where} unknown option(s): {', '.join(sorted(unknown))}")
    include = opts.get("include") or []
    exclude = opts.get("exclude") or []
    for key, value in (("include", include), ("exclude", exclude)):
        if not isinstance(value, list) or not all(isinstance(g, str) for g in value):
            raise ScanError(f"{where} '{key}' must be a list of glob strings")
    depth = opts.get("depth", 2)
    if depth not in (1, 2):
        raise ScanError(f"{where} 'depth' must be 1 or 2")
    return include, exclude, depth


def _keeper(include: list[str], exclude: list[str]):
    """Predicate over source-relative paths: hidden components and junk are
    always skipped; `exclude` globs subtract; `include` globs replace the
    default extension filter."""
    def keep(rel: str) -> bool:
        parts = Path(rel).parts
        if any(part.startswith(".") or part in SKIP_DIRS for part in parts[:-1]):
            return False
        name = parts[-1]
        if name in EXCLUDE_FILES or (name.startswith(".") and name != ".gitignore"):
            return False
        if any(fnmatch.fnmatch(rel, g) for g in exclude):
            return False
        if include:
            return any(fnmatch.fnmatch(rel, g) for g in include)
        return Path(name).suffix.lower() in DEFAULT_EXTENSIONS
    return keep


def _slugify(name: str) -> str:
    slug = SLUG_RE.sub("-", name.lower()).strip("-")
    return slug or "unit"


def _humanize(name: str) -> str:
    return re.sub(r"[-_]+", " ", name).strip().title() or name


def _files_hash(tree: dict[str, str] | None, root: Path, files: list[Path]) -> str:
    """12-hex digest over an explicit file set — committed blobs when
    available, file contents otherwise."""
    h = hashlib.sha256()
    for p in sorted(files):
        rel = p.relative_to(root).as_posix()
        sha = (tree or {}).get(rel) or sha256_file(p)
        h.update(f"{rel}:{sha}\n".encode())
    return h.hexdigest()[:12]


def _primary(files: list[Path], unit_dir: Path | None) -> Path | None:
    if not files:
        return None
    if unit_dir is not None:
        for name in ("README.md", "readme.md"):
            candidate = unit_dir / name
            if candidate in files:
                return candidate
        for stem in PRIMARY_STEMS:
            direct = [p for p in files if p.parent == unit_dir and p.stem == stem]
            if direct:
                return direct[0]
    readmes = [p for p in files if p.name.lower() == "readme.md"]
    if readmes:
        return readmes[0]
    return max(files, key=lambda p: p.stat().st_size)


def _describe(files: list[Path], unit_dir: Path | None) -> str:
    primary = _primary(files, unit_dir)
    if primary is None or primary.name.lower() != "readme.md":
        return ""
    _, body = base.parse_frontmatter(primary.read_text(errors="replace"))
    return base.first_paragraph(body)


def scan(cfg: CorpusConfig, root: Path) -> Corpus:
    if not root.is_dir():
        raise ScanError(f"corpus {cfg.name!r} source not found at {root}")
    include, exclude, depth = _options(cfg)
    keep = _keeper(include, exclude)
    tree = git_tree(root)
    repo = cfg.urls.get("repo")

    included = [
        p for p in sorted(root.rglob("*"))
        if p.is_file() and keep(p.relative_to(root).as_posix())
    ]
    if not included:
        raise ScanError(
            f"corpus {cfg.name!r}: no source files under {root} pass the include "
            f"rules — tune `adapter:` in translation.yaml"
        )

    by_top: dict[str, list[Path]] = {}
    for p in included:
        parts = p.relative_to(root).parts
        by_top.setdefault(parts[0] if len(parts) > 1 else "", []).append(p)

    if cfg.groups:
        groups = cfg.groups
        missing = [g.id for g in groups if g.id not in by_top and g.id != "root"]
        if missing:
            raise ScanError(
                f"corpus {cfg.name!r}: translation.yaml group(s) "
                f"{', '.join(missing)} match no top-level directory with "
                f"included files"
            )
    else:
        groups = [
            Group(name, _humanize(name)) for name in sorted(by_top) if name
        ]
        if "" in by_top:
            groups.append(Group("root", "Repo Root"))

    chapters: list[Chapter] = []
    for group in groups:
        group_dir = root if group.id == "root" else root / group.id
        files = by_top.get("" if group.id == "root" else group.id, [])
        if group.id == "root":
            # Loose top-level files form one chapter; subtrees are groups.
            units: list[tuple[str, Path | None, list[Path]]] = [
                ("root", None, files)
            ]
        elif depth == 1:
            units = [(group.id, group_dir, files)]
        else:
            by_sub: dict[str, list[Path]] = {}
            direct: list[Path] = []
            for p in files:
                rel_parts = p.relative_to(group_dir).parts
                if len(rel_parts) == 1:
                    direct.append(p)
                else:
                    by_sub.setdefault(rel_parts[0], []).append(p)
            units = [
                (sub, group_dir / sub, by_sub[sub]) for sub in sorted(by_sub)
            ]
            if direct:
                units.append((f"{group.id}-files", None, direct))

        seen_slugs: set[str] = set()
        for position, (name, unit_dir, unit_files) in enumerate(units, 1):
            if not unit_files:
                continue
            slug = _slugify(name)
            if slug in seen_slugs:
                raise ScanError(
                    f"corpus {cfg.name!r}: unit names {name!r} collide on slug "
                    f"{slug!r} in group {group.id!r} — rename or exclude one"
                )
            seen_slugs.add(slug)
            rel_dir = (
                unit_dir.relative_to(root).as_posix() if unit_dir is not None
                and unit_dir != root else None
            )
            chapters.append(Chapter(
                corpus=cfg.name,
                group=group.id,
                group_label=group.label,
                number=f"{position:02d}",
                slug=slug,
                title=_humanize(name),
                description=_describe(unit_files, unit_dir),
                kind="code",
                unit_paths=list(unit_files),
                primary_path=_primary(unit_files, unit_dir),
                # Branch name is a guess; corpora on a non-"main" default
                # branch should set urls.repo to a base that includes it.
                source_url=(
                    f"{repo}/tree/main/{rel_dir}" if repo and rel_dir else repo
                ),
                content_hash=_files_hash(tree, root, unit_files),
            ))

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
        groups=[g for g in groups if any(c.group == g.id for c in chapters)],
        chapters=chapters,
        source_kind="code",
        warnings=check_workdir(root, cfg.name) if tree is not None else [],
    )
