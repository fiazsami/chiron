"""Git-aware hashing shared by source adapters.

Drift hashes are derived from committed content, not working-tree bytes, so
local uncommitted edits inside a source never flag curation as stale (and
local runs agree with CI's clean checkouts). Non-git sources fall back to
hashing files on disk.
"""

import hashlib
import subprocess
from pathlib import Path

SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", "chroma_db", "node_modules"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_repo_root(root: Path) -> bool:
    """True only when root is its own repository (a submodule or standalone
    checkout). A plain folder nested inside another repo must NOT inherit
    that repo's tree/version — `git -C` would silently resolve to the parent.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return False
    return Path(out).resolve() == root.resolve()


def git_tree(root: Path) -> dict[str, str] | None:
    """Map repo-relative path -> git blob SHA at the source's HEAD.

    Returns None when git is unavailable or root is not its own repository;
    callers then fall back to hashing files on disk.
    """
    if not _is_repo_root(root):
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "--full-tree", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return None
    tree = {}
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        tree[path] = meta.split()[2]
    return tree


def _hashable_lab_file(rel: str) -> bool:
    parts = Path(rel).parts
    return not (
        parts[-1] in ("uv.lock", ".env") or any(part in SKIP_DIRS for part in parts)
    )


def lab_files(lab_dir: Path) -> list[Path]:
    files = []
    for p in sorted(lab_dir.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(lab_dir).parts):
            continue
        if p.name in ("uv.lock", ".env"):
            continue
        files.append(p)
    return files


def lab_hash(tree: dict[str, str] | None, root: Path, lab_dir: Path) -> str:
    h = hashlib.sha256()
    prefix = lab_dir.relative_to(root).as_posix() + "/"
    committed = sorted(
        (path[len(prefix):], sha)
        for path, sha in (tree or {}).items()
        if path.startswith(prefix) and _hashable_lab_file(path[len(prefix):])
    )
    if committed:
        for rel, sha in committed:
            h.update(f"{rel}:{sha}\n".encode())
    else:  # not tracked by git (or git unavailable): hash the working tree
        for p in lab_files(lab_dir):
            h.update(f"{p.relative_to(lab_dir)}:{sha256_file(p)}\n".encode())
    return h.hexdigest()


def source_version(root: Path) -> str:
    if not _is_repo_root(root):
        return "unknown"
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def check_workdir(root: Path, name: str) -> list[str]:
    """Warn when the source has uncommitted changes: page content and
    component fingerprints reflect the working tree, while drift hashes
    track the committed state, so the two can disagree until committed."""
    if not _is_repo_root(root):
        return []
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return []
    changed = [line[3:] for line in out.splitlines() if line.strip()]
    if not changed:
        return []
    sample = ", ".join(changed[:3]) + (", ..." if len(changed) > 3 else "")
    return [
        f"{name} has {len(changed)} uncommitted change(s) ({sample}): pages "
        "reflect the working tree, but drift hashes track committed content"
    ]
