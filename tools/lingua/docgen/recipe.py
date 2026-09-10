"""The recipe: how one derived tree was generated, and how to regenerate it.

A recipe is the whole contract between three parties that never talk directly:
the planning agent proposes one, chiron validates and executes it, and the
image's entrypoint reads the validated JSON and decides how to invoke the
tool. Because it is also the provenance record, it is stored inside the tree
it produced, at `.chiron/recipe.yaml`.

It deliberately carries **no timestamp**. Every byte under a derived tree
feeds some chapter's `content_hash`, and generation time is not drift — only
the source moving is.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import GROUP_BY, MAX_CHAPTERS_CAP, SCHEMA_VERSION, TOOLS, tool

RECIPE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# A digest-pinned reference. A floating tag would let the same recipe produce
# different bytes next month, which is the one thing this design cannot allow.
IMAGE_RE = re.compile(r"^[\w.\-/:]+@sha256:[0-9a-f]{64}$")


class RecipeError(Exception):
    pass


@dataclass
class Recipe:
    recipe: str  # slug; also the derived/ directory name
    tool: str
    options: dict
    image: str | None = None  # digest-pinned; None until staged
    source_commit: str | None = None  # source/ HEAD at generation
    group_by: str = "directory"
    max_chapters: int = 200
    verified: bool = False  # two staged runs produced identical bytes
    digest: str | None = None  # digest over the normalized tree

    @property
    def spec(self):
        return tool(self.tool)

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "recipe": self.recipe,
            "tool": self.tool,
            "image": self.image,
            "source_commit": self.source_commit,
            "options": dict(self.options),
            "layout": {"group_by": self.group_by, "max_chapters": self.max_chapters},
            "determinism": {"verified": self.verified, "digest": self.digest},
        }


def _check_options(spec, raw: dict, where: str) -> dict:
    """Validate against the tool's closed option schema and fill defaults.

    Unknown keys are an error rather than a warning: a recipe is written by an
    agent, and a silently dropped option is a silently different corpus.
    """
    if not isinstance(raw, dict):
        raise RecipeError(f"{where}: 'options' must be a mapping")
    unknown = sorted(set(raw) - set(spec.options))
    if unknown:
        raise RecipeError(
            f"{where}: unknown option(s) for {spec.slug}: {', '.join(unknown)} "
            f"— accepted: {', '.join(sorted(spec.options))}"
        )
    out: dict = {}
    for name, opt in spec.options.items():
        # An explicit null reads as "not set" — `dump` writes the filled
        # defaults back out, so a recipe must survive its own round trip.
        if name not in raw or raw[name] is None:
            if opt.required:
                raise RecipeError(
                    f"{where}: {spec.slug} requires option {name!r} ({opt.doc})"
                )
            out[name] = [] if opt.default is None and opt.kind is list else opt.default
            if isinstance(opt.default, list):
                out[name] = list(opt.default)
            continue
        value = raw[name]
        # bool is a subclass of int; check it first or `int` options accept True.
        if opt.kind is bool and not isinstance(value, bool):
            raise RecipeError(f"{where}: option {name!r} must be a boolean")
        if opt.kind is not bool and isinstance(value, bool):
            raise RecipeError(
                f"{where}: option {name!r} must be a {opt.kind.__name__}, got a boolean"
            )
        if not isinstance(value, opt.kind):
            raise RecipeError(
                f"{where}: option {name!r} must be a {opt.kind.__name__}, "
                f"got {type(value).__name__}"
            )
        if opt.kind is list:
            if not all(isinstance(v, opt.member) for v in value):
                raise RecipeError(
                    f"{where}: option {name!r} must be a list of "
                    f"{opt.member.__name__}"
                )
            for v in value:
                _check_relpath(v, f"{where}: option {name!r}")
            value = list(value)
        out[name] = value
    return out


def _check_relpath(value: str, where: str) -> None:
    """Recipe paths address the read-only source mount, so they stay relative
    and inside it. An absolute path or a `..` would reach out of the corpus."""
    if value.startswith("/"):
        raise RecipeError(f"{where}: {value!r} must be source-relative, not absolute")
    if ".." in Path(value).parts:
        raise RecipeError(f"{where}: {value!r} must not escape the source with '..'")


def parse(data: dict, where: str) -> Recipe:
    """Validate a recipe mapping — from an agent's JSON or from disk."""
    if not isinstance(data, dict):
        raise RecipeError(f"{where}: expected a mapping")

    schema = data.get("schema", SCHEMA_VERSION)
    if schema != SCHEMA_VERSION:
        raise RecipeError(
            f"{where}: recipe schema {schema} — this chiron speaks "
            f"{SCHEMA_VERSION}"
        )

    slug = data.get("recipe")
    if not isinstance(slug, str) or not RECIPE_RE.fullmatch(slug):
        raise RecipeError(
            f"{where}: 'recipe' is required and must match {RECIPE_RE.pattern} "
            f"(it names the derived/<recipe>/ directory), got {slug!r}"
        )

    slug_tool = data.get("tool")
    if not isinstance(slug_tool, str) or slug_tool not in TOOLS:
        raise RecipeError(
            f"{where}: 'tool' must be one of {', '.join(sorted(TOOLS))}, "
            f"got {slug_tool!r}"
        )
    spec = TOOLS[slug_tool]

    image = data.get("image")
    if image is not None and (not isinstance(image, str) or not IMAGE_RE.fullmatch(image)):
        raise RecipeError(
            f"{where}: 'image' must be digest-pinned (name@sha256:<64 hex>) — "
            f"a floating tag cannot produce reproducible bytes; got {image!r}"
        )

    commit = data.get("source_commit")
    if commit is not None and not isinstance(commit, str):
        raise RecipeError(f"{where}: 'source_commit' must be a string")

    layout = data.get("layout") or {}
    if not isinstance(layout, dict):
        raise RecipeError(f"{where}: 'layout' must be a mapping")
    unknown = sorted(set(layout) - {"group_by", "max_chapters"})
    if unknown:
        raise RecipeError(f"{where}: unknown layout key(s): {', '.join(unknown)}")
    group_by = layout.get("group_by", "directory")
    if group_by not in GROUP_BY:
        raise RecipeError(
            f"{where}: layout.group_by must be one of {', '.join(GROUP_BY)}, "
            f"got {group_by!r}"
        )
    max_chapters = layout.get("max_chapters", 200)
    if isinstance(max_chapters, bool) or not isinstance(max_chapters, int):
        raise RecipeError(f"{where}: layout.max_chapters must be an integer")
    if not 1 <= max_chapters <= MAX_CHAPTERS_CAP:
        raise RecipeError(
            f"{where}: layout.max_chapters must be 1..{MAX_CHAPTERS_CAP} — "
            f"every chapter is an authoring request, so the cap is a budget"
        )

    det = data.get("determinism") or {}
    if not isinstance(det, dict):
        raise RecipeError(f"{where}: 'determinism' must be a mapping")

    return Recipe(
        recipe=slug,
        tool=slug_tool,
        options=_check_options(spec, data.get("options") or {}, where),
        image=image,
        source_commit=commit,
        group_by=group_by,
        max_chapters=max_chapters,
        verified=bool(det.get("verified", False)),
        digest=det.get("digest"),
    )


def load_json(path: Path) -> Recipe:
    """Read a recipe an agent wrote — the `--from` side of `ch doc --stage`."""
    where = str(path)
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        raise RecipeError(f"{where}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RecipeError(f"{where}: not valid JSON: {exc}") from exc
    return parse(data, where)


def load(tree: Path) -> Recipe:
    """Read the recipe stored inside a derived tree."""
    path = tree / ".chiron" / "recipe.yaml"
    where = str(path)
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RecipeError(f"{where}: {exc}") from exc
    return parse(data, where)


def dump(recipe: Recipe, tree: Path) -> Path:
    """Write the recipe into the tree it produced."""
    path = tree / ".chiron" / "recipe.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Generated by `ch doc` — the provenance of this tree and the recipe\n"
        "# that regenerates it. Do not hand-edit; re-stage instead.\n"
        + yaml.safe_dump(recipe.to_dict(), sort_keys=False)
    )
    return path
