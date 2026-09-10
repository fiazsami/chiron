"""The determinism pass — the reason this feature can have a state model.

Every anchor is pinned to its chapter's `content_hash`, computed over the
chapter's bytes. Generators sign their output: TypeDoc stamps its version,
Doxygen stamps a date, and everything embeds the absolute path of the
directory it read. Left alone, each of those turns one regeneration into
"every entry in this corpus is now stale" — the drift signal would stop
meaning anything.

So a staged tree is normalized before it is ever hashed: strip what varies
with the run, keep what varies with the source. `ch doc --stage` then proves
the result by generating twice and comparing, and refuses to promote a tree
whose bytes moved on their own.
"""

import hashlib
import re
from pathlib import Path

from . import COMMON_STRIP, ToolSpec

# Pages a generator emits with nothing in them: a heading and no prose. They
# carry no working language, and they are exactly where tools differ from run
# to run (ordering of an empty index, a stray nav stub).
_HEADING_ONLY = re.compile(r"^\s*#{1,6}[^\n]*\s*$")
BLANK_RUN = re.compile(r"\n{3,}")
TRAILING_WS = re.compile(r"[ \t]+$", re.M)


def normalize_text(text: str, spec: ToolSpec) -> str:
    """Apply the common rules, then the tool's own, then tidy whitespace."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for pattern, repl in COMMON_STRIP:
        text = pattern.sub(repl, text)
    for pattern, repl in spec.strip:
        text = pattern.sub(repl, text)
    text = TRAILING_WS.sub("", text)
    text = BLANK_RUN.sub("\n\n", text)
    return text.strip() + "\n"


def is_empty_page(text: str) -> bool:
    """True when nothing survives but headings and whitespace."""
    body = [ln for ln in text.splitlines() if ln.strip()]
    return not body or all(_HEADING_ONLY.fullmatch(ln) for ln in body)


def normalize_tree(tree: Path, spec: ToolSpec) -> tuple[int, int]:
    """Normalize every .md under `tree` in place; drop the empty ones.

    Returns (normalized, dropped). Directories emptied by the drop are pruned,
    because an empty directory is a group with no chapters.
    """
    normalized = dropped = 0
    for path in sorted(tree.rglob("*.md")):
        if any(p.startswith(".") for p in path.relative_to(tree).parts):
            continue
        text = normalize_text(path.read_text(errors="replace"), spec)
        if is_empty_page(text):
            path.unlink()
            dropped += 1
            continue
        path.write_text(text)
        normalized += 1
    for directory in sorted(tree.rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return normalized, dropped


def tree_digest(tree: Path) -> str:
    """A digest over the tree's Markdown, path and content, sorted.

    This is what two staged runs are compared on, and what the recipe records
    once a tool has proved itself deterministic. `.chiron/` is excluded — the
    recipe records this digest, so it cannot also be inside it.
    """
    h = hashlib.sha256()
    for path in sorted(tree.rglob("*.md")):
        rel = path.relative_to(tree)
        if any(p.startswith(".") for p in rel.parts):
            continue
        h.update(rel.as_posix().encode())
        h.update(b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def first_difference(a: Path, b: Path) -> str | None:
    """The first way two staged trees disagree, in words a gate can print.

    Reported as one finding rather than a full diff: what the human needs is
    'which tool is non-deterministic and where', not every line of it.
    """
    files_a = {p.relative_to(a).as_posix() for p in a.rglob("*.md")}
    files_b = {p.relative_to(b).as_posix() for p in b.rglob("*.md")}
    only_a = sorted(files_a - files_b)
    only_b = sorted(files_b - files_a)
    if only_a or only_b:
        return (
            f"the two runs produced different files — "
            f"first run only: {', '.join(only_a[:3]) or '—'} · "
            f"second run only: {', '.join(only_b[:3]) or '—'}"
        )
    for rel in sorted(files_a):
        left = (a / rel).read_text(errors="replace").splitlines()
        right = (b / rel).read_text(errors="replace").splitlines()
        for lineno, (l, r) in enumerate(zip(left, right), 1):
            if l != r:
                return (
                    f"{rel}:{lineno} differs between runs\n"
                    f"    run 1: {l[:100]}\n"
                    f"    run 2: {r[:100]}"
                )
        if len(left) != len(right):
            return f"{rel} differs in length between runs ({len(left)} vs {len(right)} lines)"
    return None
