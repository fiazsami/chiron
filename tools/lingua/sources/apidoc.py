"""Adapter for a generated documentation tree — the output of `ch doc`.

A derived tree is Markdown, so most of this could have delegated to
`sources.markdown`. It does not, for two reasons: generated trees nest deeper
than `<group>/<doc>.md`, and their `index`/`README` pages are the module
overviews — the most valuable pages in the tree — where the markdown block
skips those stems.

Chaptering is deterministic in the same sense `codetree` means it: the same
tree always yields the same chapters, so anchors stay put. Nothing here reads
the clock, the filesystem order, or a file's size.

A register's tools/adapter.py delegates here in four lines:

    from tools.lingua.sources import apidoc

    def scan(cfg, root):
        return apidoc.scan(cfg, root)

The recipe at <root>/.chiron/recipe.yaml supplies `group_by` and
`max_chapters`; `adapter:` in translation.yaml may override the grouping when
a generator's own layout wants regrouping.
"""

import hashlib
import re
from pathlib import Path

from tools.lingua.corpora import CorpusConfig
from tools.lingua.docgen import recipe as recipe_mod
from tools.lingua.gittree import check_workdir, git_tree, sha256_file, source_version
from tools.lingua.model import RESERVED_GROUP_IDS, Chapter, Corpus, Group, ScanError
from tools.lingua.sources import base

SLUG_RE = re.compile(r"[^a-z0-9-]+")
PRIMARY_STEMS = ("index", "readme", "modules", "globals", "_index")
# A generated tree's own metadata, never material.
META_DIR = ".chiron"


def _options(cfg: CorpusConfig) -> tuple[str | None, int | None]:
    opts = dict(cfg.adapter_options)
    where = f"corpora/{cfg.name}/{cfg.register}/translation.yaml adapter:"
    unknown = set(opts) - {"group_by", "max_chapters"}
    if unknown:
        raise ScanError(f"{where} unknown option(s): {', '.join(sorted(unknown))}")
    group_by = opts.get("group_by")
    if group_by is not None and group_by not in ("directory", "module"):
        raise ScanError(f"{where} 'group_by' must be 'directory' or 'module'")
    max_chapters = opts.get("max_chapters")
    if max_chapters is not None and (
        isinstance(max_chapters, bool) or not isinstance(max_chapters, int)
    ):
        raise ScanError(f"{where} 'max_chapters' must be an integer")
    return group_by, max_chapters


def _slugify(name: str) -> str:
    slug = SLUG_RE.sub("-", name.lower()).strip("-")
    return slug or "unit"


def _humanize(name: str) -> str:
    return re.sub(r"[-_]+", " ", name).strip().title() or name


def _files_hash(tree: dict[str, str] | None, root: Path, files: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(files):
        rel = p.relative_to(root).as_posix()
        sha = (tree or {}).get(rel) or sha256_file(p)
        h.update(f"{rel}:{sha}\n".encode())
    return h.hexdigest()[:12]


def _primary(files: list[Path]) -> Path:
    """A module overview if the generator wrote one, else the first page.

    Deliberately not "the largest file": size ties break arbitrarily, and an
    arbitrary primary is an arbitrary title.
    """
    for stem in PRIMARY_STEMS:
        for p in files:
            if p.stem.lower() == stem:
                return p
    return files[0]


def _source_url(repo: str | None, text: str) -> str | None:
    """Point at the upstream file this page documents, not at the page.

    Generators record the defining file in a `Defined in` line; when one is
    there the reader should land on real code. Failing that, the repo root is
    more honest than a link to a generated artifact.
    """
    if not repo:
        return None
    m = re.search(
        r"^(?:\*?\*?Defined in:?\*?\*?|Source:)\s*\[?([\w./-]+\.\w+)(?::(\d+))?",
        text, re.M | re.I,
    )
    if m:
        line = f"#L{m.group(2)}" if m.group(2) else ""
        return f"{repo}/blob/main/{m.group(1).lstrip('./')}{line}"
    return repo


def scan(cfg: CorpusConfig, root: Path) -> Corpus:
    if not root.is_dir():
        raise ScanError(
            f"corpus {cfg.name!r}: derived tree not found at {root} — "
            f"promote one with `./ch doc --promote`"
        )
    opt_group_by, opt_max = _options(cfg)
    try:
        rcp = recipe_mod.load(root)
    except recipe_mod.RecipeError as exc:
        raise ScanError(f"corpus {cfg.name!r}: {exc}") from exc
    group_by = opt_group_by or rcp.group_by
    max_chapters = opt_max or rcp.max_chapters

    pages = [
        p for p in sorted(root.rglob("*.md"))
        if not any(part.startswith(".") for part in p.relative_to(root).parts)
    ]
    if not pages:
        raise ScanError(
            f"corpus {cfg.name!r}: no Markdown under {root} — the generator "
            f"produced nothing, or the normalizer dropped it all as empty"
        )

    # Group = top-level directory; loose top-level pages form "reference".
    # "reference" rather than "root": `api` is a reserved group id, and a
    # generated tree's loose pages are its reference surface.
    by_group: dict[str, list[Path]] = {}
    for p in pages:
        parts = p.relative_to(root).parts
        by_group.setdefault(parts[0] if len(parts) > 1 else "reference", []).append(p)

    reserved = sorted(set(by_group) & RESERVED_GROUP_IDS)
    if reserved:
        plural = len(reserved) > 1
        raise ScanError(
            f"corpus {cfg.name!r}: the generated tree has top-level "
            f"director{'ies' if plural else 'y'} {', '.join(reserved)}, which "
            f"{'shadow' if plural else 'shadows'} viewer routes — regroup with "
            f"`adapter: {{group_by: module}}` or re-stage with a narrower scope"
        )

    if cfg.groups:
        groups = cfg.groups
        missing = [g.id for g in groups if g.id not in by_group]
        if missing:
            raise ScanError(
                f"corpus {cfg.name!r}: translation.yaml group(s) "
                f"{', '.join(missing)} match no directory in the derived tree"
            )
    else:
        groups = [Group(_slugify(g), _humanize(g)) for g in sorted(by_group)]

    tree = git_tree(root)
    repo = cfg.urls.get("repo")
    chapters: list[Chapter] = []

    for group in groups:
        raw_key = next((k for k in by_group if _slugify(k) == group.id), group.id)
        files = by_group.get(raw_key, [])
        if not files:
            continue
        group_dir = root if raw_key == "reference" else root / raw_key

        if group_by == "module":
            # One chapter per immediate subdirectory; the group's own loose
            # pages cluster into one. Mirrors codetree's depth=2.
            units: dict[str, list[Path]] = {}
            for p in files:
                rel_parts = p.relative_to(group_dir).parts
                key = rel_parts[0] if len(rel_parts) > 1 else raw_key
                units.setdefault(key, []).append(p)
            unit_list = [(k, v) for k, v in sorted(units.items())]
        else:  # directory: one chapter per page — the generator's own units
            unit_list = [(p.relative_to(group_dir).as_posix()[:-3], [p])
                         for p in files]

        seen: set[str] = set()
        for position, (name, unit_files) in enumerate(unit_list, 1):
            slug = _slugify(name)
            if slug in seen:
                raise ScanError(
                    f"corpus {cfg.name!r}: unit {name!r} collides on slug "
                    f"{slug!r} in group {group.id!r}"
                )
            seen.add(slug)
            primary = _primary(unit_files)
            text = primary.read_text(errors="replace")
            _, body = base.parse_frontmatter(text)
            chapters.append(Chapter(
                corpus=cfg.name,
                group=group.id,
                group_label=group.label,
                number=f"{position:02d}",
                slug=slug,
                title=base.h1_title(body, _humanize(name)),
                description=base.first_paragraph(body),
                kind="doc",
                unit_paths=list(unit_files),
                primary_path=primary,
                source_url=_source_url(repo, text),
                content_hash=_files_hash(tree, root, unit_files),
            ))

    if len(chapters) > max_chapters:
        raise ScanError(
            f"corpus {cfg.name!r}: the derived tree yields {len(chapters)} "
            f"chapters, over this recipe's max_chapters of {max_chapters}. "
            f"Every chapter is an authoring request, so this cap is a budget: "
            f"re-stage with a narrower scope, set "
            f"`adapter: {{group_by: module}}` to aggregate, or raise the cap "
            f"in {root}/.chiron/recipe.yaml"
        )

    checkout = source_version(root)
    if checkout == "unknown":
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
        # Generated or not, this material is Markdown. Saying so keeps the
        # manifest at v6 and the viewer unchanged.
        source_kind="markdown",
        warnings=check_workdir(root, cfg.name) if tree is not None else [],
    )
