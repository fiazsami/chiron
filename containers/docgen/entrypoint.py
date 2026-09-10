#!/usr/bin/env python3
"""Turn a validated recipe into a documentation tree. Runs inside the image.

Contract with chiron: read /recipe.json — already schema-checked on the host —
write Markdown under /out, exit non-zero with a reason on failure.
Never read anything outside /src, never write anything outside /out, never
touch the network (there is none).

Everything here is written for reproducibility rather than for beauty: sorted
iteration, no timestamps, no absolute paths in output where a flag can prevent
them. What cannot be prevented at generation time, chiron's normalizer strips
afterward. Both halves are needed — the normalizer cannot fix a page that got
written in a different order.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path("/src")
OUT = Path("/out")
# Input, mounted read-only. Never inside /out: generators empty their output
# directory before writing, and typedoc produces nothing when it cannot.
RECIPE = Path("/recipe.json")
# Generators write here, not to /out. Several of them delete and recreate
# their output directory, which cannot work on a bind-mount point — typedoc
# warns "Could not empty the output directory" and then writes nothing at all.
# Giving each tool a directory it fully owns sidesteps the whole class.
GEN = Path(os.environ.get("TMPDIR", "/tmp")) / "gen"
TMP = Path(os.environ.get("TMPDIR", "/tmp"))


def fail(message: str) -> None:
    print(f"docgen: {message}", file=sys.stderr)
    raise SystemExit(3)


def run(argv: list[str], cwd: Path | None = None, env: dict | None = None) -> str:
    """Run a generator. Its stderr is the user's error message when it fails."""
    proc = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True,
        env={**os.environ, **(env or {})},
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-25:]
        fail(f"{argv[0]} exited {proc.returncode}:\n  " + "\n  ".join(tail))
    return proc.stdout


def resolve(rel: str) -> Path:
    """A recipe path, resolved under /src and proved to stay there.

    chiron rejects absolute paths and `..` before we ever see them; this is the
    second lock, because the first one lives on the other side of a mount.
    """
    path = (SRC / rel).resolve()
    if not path.is_relative_to(SRC.resolve()):
        fail(f"{rel!r} resolves outside /src")
    return path


def write(rel: str, text: str) -> None:
    path = GEN / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# --- typedoc ---------------------------------------------------------------

def typedoc(opts: dict) -> None:
    argv = [
        "typedoc",
        "--plugin", "typedoc-plugin-markdown",
        "--out", str(GEN),
        # Git state would leak the checkout into every source link, and the
        # tree is hashed. --disableGit demands an explicit link template, and
        # a source-relative one is exactly what chiron parses back into an
        # upstream URL — so the constraint lands where we wanted to be anyway.
        "--disableGit",
        "--sourceLinkTemplate", "{path}#L{line}",
        "--basePath", str(SRC),
        "--hideGenerator",
        "--githubPages", "false",
        "--readme", "none",
        "--skipErrorChecking",
    ]
    if opts.get("documented_only"):
        argv.append("--excludeNotDocumented")
    if not opts.get("include_private"):
        argv += ["--excludePrivate", "--excludeInternal"]
    for pattern in opts.get("exclude") or []:
        argv += ["--exclude", pattern]
    if opts.get("tsconfig"):
        argv += ["--tsconfig", str(resolve(opts["tsconfig"]))]
    argv += ["--entryPoints", *[str(resolve(p)) for p in opts["entry_points"]]]
    run(argv, cwd=SRC)


# --- pydoc-markdown --------------------------------------------------------

def pydoc_markdown(opts: dict) -> None:
    search = [str(resolve(p)) for p in (opts.get("search_path") or ["."])]
    wrote = 0
    for package in sorted(opts["packages"]):
        modules = _python_modules(package, search)
        if not modules:
            fail(f"package {package!r} has no modules under {', '.join(search)}")
        for module in modules:
            # No --render-toc: a per-page table of contents is scaffolding,
            # and its "# Table of Contents" heading would become the chapter
            # title, since chiron takes a title from the first H1.
            argv = ["pydoc-markdown"]
            for path in search:
                argv += ["-I", path]
            argv += ["-m", module]
            text = run(argv, cwd=SRC)
            if not text.strip():
                continue
            rel = module.replace(".", "/") + ".md"
            write(rel, text)
            wrote += 1
    if not wrote:
        fail("pydoc-markdown produced no pages")


def _python_modules(package: str, search: list[str]) -> list[str]:
    """Every importable module under a package, sorted. Deterministic walk."""
    found: list[str] = []
    for root in search:
        base = Path(root) / package.replace(".", "/")
        if not base.is_dir():
            if (Path(root) / (package.replace(".", "/") + ".py")).is_file():
                found.append(package)
            continue
        for path in sorted(base.rglob("*.py")):
            if any(p.startswith(".") or p == "__pycache__" for p in path.parts):
                continue
            rel = path.relative_to(Path(root)).with_suffix("")
            parts = list(rel.parts)
            if parts[-1] == "__init__":
                parts.pop()
            if parts:
                found.append(".".join(parts))
    return sorted(set(found))


# --- gomarkdoc -------------------------------------------------------------

def gomarkdoc(opts: dict) -> None:
    # Go insists on a writable cache and a writable module tree; /src is
    # read-only, so work from a copy in tmpfs.
    work = TMP / "gosrc"
    shutil.copytree(SRC, work, symlinks=True, dirs_exist_ok=True)
    argv = ["gomarkdoc", "--output", str(GEN / "{{.Dir}}" / "index.md")]
    if opts.get("include_unexported"):
        argv.append("--include-unexported")
    argv += list(opts.get("packages") or ["./..."])
    # No GOFLAGS: gomarkdoc parses the variable itself and rejects go's flags.
    run(argv, cwd=work, env={"GOCACHE": str(TMP / "gocache"),
                             "GOMODCACHE": str(TMP / "gomod")})


# --- doxygen -> XML -> moxygen ---------------------------------------------

DOXYFILE = """\
PROJECT_NAME           = corpus
INPUT                  = {inputs}
RECURSIVE              = {recursive}
EXCLUDE_PATTERNS       = {exclude}
GENERATE_XML           = YES
XML_OUTPUT             = {xml}
GENERATE_HTML          = NO
GENERATE_LATEX         = NO
HAVE_DOT               = NO
QUIET                  = YES
WARN_IF_UNDOCUMENTED   = NO
HIDE_UNDOC_MEMBERS     = {hide_undoc}
HIDE_UNDOC_CLASSES     = {hide_undoc}
EXTRACT_PRIVATE        = {private}
EXTRACT_ALL            = {extract_all}
# Sorting and stamping are the two things that make doxygen non-reproducible.
SORT_MEMBER_DOCS       = YES
SORT_BRIEF_DOCS        = YES
SORT_MEMBERS_CTORS_1ST = YES
HTML_TIMESTAMP         = NO
"""


def doxygen(opts: dict) -> None:
    xml = TMP / "xml"
    documented_only = opts.get("documented_only", True)
    doxyfile = TMP / "Doxyfile"
    doxyfile.write_text(DOXYFILE.format(
        inputs=" ".join(f'"{resolve(p)}"' for p in opts["input"]),
        recursive="YES" if opts.get("recursive", True) else "NO",
        exclude=" ".join(f'"{p}"' for p in (opts.get("exclude_patterns") or [])),
        xml=xml,
        hide_undoc="YES" if documented_only else "NO",
        private="YES" if opts.get("extract_private") else "NO",
        extract_all="NO" if documented_only else "YES",
    ))
    run(["doxygen", str(doxyfile)], cwd=SRC)
    if not (xml / "index.xml").is_file():
        fail("doxygen produced no XML — check the `input` directories")
    # One page per class, so a chapter is a unit of the API rather than one
    # enormous api.md, and --noindex drops moxygen's nav, which carries no
    # working language. Not --groups: moxygen exits 1 when it is asked for
    # groups and the project uses no @defgroup, which most do not.
    run(["moxygen", "--classes", "--anchors", "--noindex",
         "--output", str(GEN / "%s.md"), str(xml)])


TOOLS = {
    "typedoc": typedoc,
    "pydoc-markdown": pydoc_markdown,
    "gomarkdoc": gomarkdoc,
    "doxygen": doxygen,
}


def main() -> int:
    if not RECIPE.is_file():
        fail(f"{RECIPE} is missing — chiron mounts it before the run")
    recipe = json.loads(RECIPE.read_text())
    tool = recipe.get("tool")
    if tool not in TOOLS:
        fail(f"this image does not implement {tool!r} "
             f"(has: {', '.join(sorted(TOOLS))})")
    # Reproducible builds ask for this, and several toolchains honour it.
    os.environ.setdefault("SOURCE_DATE_EPOCH", "0")
    os.environ.setdefault("TZ", "UTC")
    GEN.mkdir(parents=True, exist_ok=True)
    TOOLS[tool](recipe.get("options") or {})

    pages = sorted(
        p for p in GEN.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(GEN).parts)
    )
    if not pages:
        fail(f"{tool} wrote no Markdown — nothing to mount")
    # Sorted so the copy order is stable; the bytes are what get hashed, but a
    # stable walk keeps anything order-sensitive downstream honest too.
    for page in pages:
        target = OUT / page.relative_to(GEN)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(page, target)
    print(f"docgen: {tool} wrote {len(pages)} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
