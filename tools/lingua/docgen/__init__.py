"""Generated documentation as corpus material.

A doc generator reads a codebase and emits prose organized by symbol. That
prose is what chiron wants from an undocumented repo: the identifiers are the
working language, and the doc comments are the authors describing it in their
own words. So `ch doc` runs one in a pinned container and writes a Markdown
tree beside `source/`; from the adapter down nothing knows the material was
generated.

Three rules shape this package:

1. **The registry is closed.** A recipe may name only a `tool` and only the
   option keys declared here. The planning agent proposes a recipe; it never
   proposes a command. Nothing free-form reaches a shell.
2. **Determinism is the whole feature.** Every anchor is pinned to its
   chapter's `content_hash`, so a generator that emits a timestamp would mark
   the entire corpus stale on every run. `normalize` strips what varies and
   `ch doc --stage` proves it by generating twice.
3. **The recipe is the contract with the image.** chiron validates it; the
   image's entrypoint reads the validated JSON and decides how to invoke the
   tool. One schema between them, versioned — not two flag tables to drift
   apart.
"""

import re
from dataclasses import dataclass

SCHEMA_VERSION = 1

# Rules applied to every generated page whatever produced it. Ordered.
COMMON_STRIP: tuple[tuple[re.Pattern, str], ...] = (
    # Any absolute path to the container's read-only source mount. These are
    # the single biggest source of spurious drift: the same tree generated
    # under a different mount point would hash differently.
    (re.compile(r"/src/"), ""),
    # ISO-8601 and RFC-1123-ish stamps generators like to sign their work with.
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?"), ""),
    (re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \w{3} +\d{1,2} \d{2}:\d{2}:\d{2} \d{4}\b"), ""),
)


@dataclass(frozen=True)
class Option:
    """One recipe option: what it is, whether it must be given, its default.

    `kind` is a python type the loaded YAML/JSON value must already be —
    recipes are data, so nothing is coerced. A wrong type is a rejection, not
    a conversion.
    """

    kind: type  # list, str, bool, int
    doc: str
    required: bool = False
    default: object = None
    member: type | None = None  # for list options: the element type


@dataclass(frozen=True)
class ToolSpec:
    slug: str
    label: str
    # Extensions this tool serves — what the census matches against.
    extensions: tuple[str, ...]
    # Build manifests whose presence argues for this tool, strongest first.
    manifests: tuple[str, ...]
    options: dict[str, Option]
    # Tool-specific normalizer rules, applied after COMMON_STRIP.
    strip: tuple[tuple[re.Pattern, str], ...] = ()
    notes: str = ""


TOOLS: dict[str, ToolSpec] = {
    "typedoc": ToolSpec(
        slug="typedoc",
        label="TypeDoc + typedoc-plugin-markdown",
        extensions=(".ts", ".tsx", ".mts", ".cts", ".js", ".jsx"),
        manifests=("tsconfig.json", "package.json"),
        options={
            "entry_points": Option(
                list, "source-relative entry modules", required=True, member=str
            ),
            "tsconfig": Option(str, "source-relative tsconfig to type against"),
            "exclude": Option(list, "glob patterns to skip", default=[], member=str),
            "documented_only": Option(
                bool,
                "drop symbols with no doc comment — generator scaffolding is "
                "not working language",
                default=True,
            ),
            "include_private": Option(bool, "keep private members", default=False),
        },
        strip=(
            # TypeDoc signs every page with its own version.
            (re.compile(r"^\*\*\*$\n+^Generated using \[typedoc.*$", re.M | re.I), ""),
            (re.compile(r"^Generated using \[TypeDoc\].*$", re.M), ""),
        ),
        notes="Emits Markdown natively via typedoc-plugin-markdown.",
    ),
    "pydoc-markdown": ToolSpec(
        slug="pydoc-markdown",
        label="pydoc-markdown",
        extensions=(".py", ".pyi"),
        manifests=("pyproject.toml", "setup.py", "setup.cfg"),
        options={
            "packages": Option(
                list, "importable package names to document", required=True, member=str
            ),
            "search_path": Option(
                list, "source-relative roots to import from", default=["."], member=str
            ),
            "documented_only": Option(
                bool, "drop symbols with no docstring", default=True
            ),
            "include_private": Option(
                bool, "keep _underscore members", default=False
            ),
        },
        notes="Emits Markdown natively.",
    ),
    "gomarkdoc": ToolSpec(
        slug="gomarkdoc",
        label="gomarkdoc",
        extensions=(".go",),
        manifests=("go.mod",),
        options={
            "packages": Option(
                list, "package patterns", default=["./..."], member=str
            ),
            "include_unexported": Option(
                bool, "document unexported identifiers", default=False
            ),
        },
        strip=((re.compile(r"^Generated by \[gomarkdoc\].*$", re.M), ""),),
        notes="Emits Markdown natively.",
    ),
    "doxygen": ToolSpec(
        slug="doxygen",
        label="Doxygen → XML → moxygen",
        extensions=(".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"),
        manifests=("Doxyfile", "CMakeLists.txt", "Makefile", "meson.build"),
        options={
            "input": Option(
                list, "source-relative directories to scan", required=True, member=str
            ),
            "recursive": Option(bool, "descend into subdirectories", default=True),
            "exclude_patterns": Option(
                list, "patterns to skip", default=[], member=str
            ),
            "documented_only": Option(
                bool, "hide undocumented members and classes", default=True
            ),
            "extract_private": Option(bool, "keep private members", default=False),
        },
        strip=(
            (re.compile(r"^Generated by Doxygen.*$", re.M), ""),
            (re.compile(r"^Generated on .* for .* by.*$", re.M), ""),
        ),
        notes=(
            "Doxygen has no Markdown backend; the image converts its XML with "
            "moxygen."
        ),
    ),
}

# Doxide is the other credible C++ path and emits Markdown natively, but it
# needs a source build (cmake, libclang, yaml-cpp, ICU) that this image does
# not carry. It is left out rather than listed-and-broken: the registry being
# closed only means something if everything in it runs.

# Group ids a generated tree must not produce — they shadow viewer routes.
# Mirrors model.RESERVED_GROUP_IDS; imported there rather than restated when
# apidoc chapters are built.
GROUP_BY = ("directory", "module")
MAX_CHAPTERS_CAP = 500


def tool(slug: str) -> ToolSpec:
    """Look up a tool, with the closed registry named in the error."""
    spec = TOOLS.get(slug)
    if spec is None:
        raise KeyError(
            f"unknown tool {slug!r} — the registry is closed: "
            f"{', '.join(sorted(TOOLS))}"
        )
    return spec
