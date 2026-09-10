"""Stage, prove, and promote a derived tree.

The order matters and is the point:

    generate -> normalize -> generate again -> compare -> promote

A recipe that has not proved itself deterministic is generated twice and the
two trees compared. Only then can it be promoted, and only then does the
recipe record `verified: true` so later runs pay once. A tree whose bytes move
on their own would mark every anchor in the corpus stale on every
regeneration, so this is the check the whole feature rests on.

Staging lives at corpora/<name>/.staging/<recipe>/ — outside every tree the
pipeline scans, so a half-finished generation is never mountable.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..gittree import source_version
from . import TOOLS
from .normalize import first_difference, normalize_tree, tree_digest
from .recipe import Recipe, dump, load_json

# The staged recipe, carried in the tree so `--promote` can be its own
# invocation — the gate between them is a human reading the staged output.
STAGED = ".chiron/staged.json"


@dataclass
class Staged:
    tree: Path
    recipe: Recipe
    pages: int
    dropped: int
    digest: str
    proved: bool  # this run generated twice and the trees matched
    difference: str | None = None  # set when the two runs disagreed

    @property
    def ok(self) -> bool:
        return self.difference is None


def staging_dir(corpus_dir: Path, recipe: str) -> Path:
    return corpus_dir / ".staging" / recipe


def derived_dir(corpus_dir: Path, recipe: str) -> Path:
    return corpus_dir / "derived" / recipe


def _clear(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def stage(recipe: Recipe, corpus_dir: Path, *, generate, echo=print) -> Staged:
    """Generate into staging and, unless already proved, prove determinism.

    `generate(recipe, source, out)` is injected so this logic is testable
    without a container.
    """
    source = corpus_dir / "source"
    spec = TOOLS[recipe.tool]
    tree = staging_dir(corpus_dir, recipe.recipe)

    _clear(tree)
    echo(f"generating with {recipe.tool} …")
    generate(recipe, source, tree)
    pages, dropped = normalize_tree(tree, spec)
    digest = tree_digest(tree)
    echo(f"  {pages} page(s), {dropped} empty page(s) dropped · digest {digest[:12]}")

    if recipe.verified and recipe.digest:
        # Already proved once. Still catch a tool that changed under us.
        recipe.source_commit = source_version(source)
        recipe.digest = digest
        return _remember(Staged(tree, recipe, pages, dropped, digest, proved=False))

    echo("proving determinism — generating a second time …")
    second = staging_dir(corpus_dir, recipe.recipe + ".verify")
    _clear(second)
    try:
        generate(recipe, source, second)
        normalize_tree(second, spec)
        difference = None if tree_digest(second) == digest else first_difference(tree, second)
    finally:
        shutil.rmtree(second, ignore_errors=True)

    if difference is None:
        echo("  identical — this recipe is deterministic")
    recipe.verified = difference is None
    recipe.digest = digest if difference is None else None
    recipe.source_commit = source_version(source)
    return _remember(Staged(tree, recipe, pages, dropped, digest, proved=True,
                            difference=difference))


def _remember(staged: Staged) -> Staged:
    """Persist the staged recipe inside the tree. Dot-paths are excluded from
    the digest and from chaptering, so this never becomes material."""
    path = staged.tree / STAGED
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(staged.recipe.to_dict(), indent=2))
    return staged


def staged_recipe(tree: Path) -> Recipe:
    """Read back what `stage` left. Raises RecipeError if it is not there."""
    return load_json(tree / STAGED)


def promote(staged: Staged, corpus_dir: Path, *, echo=print) -> Path:
    """Move a proved staging tree into derived/, committed.

    The tree is git-initialised so every existing code path treats it as an
    ordinary checkout — gittree hashes its committed blobs, source_version
    reports a real version, check_workdir warns on hand edits. It also means
    `git -C derived/<recipe> diff` answers "what changed in the docs when the
    source moved", which no other record of a regeneration would.
    """
    if not staged.ok:
        raise ValueError("refusing to promote a tree that failed its determinism check")
    target = derived_dir(corpus_dir, staged.recipe.recipe)
    existing_git = target / ".git"
    carried = None
    if existing_git.is_dir():
        # Keep the history: this recipe has been promoted before, and the diff
        # between generations is the useful artifact.
        carried = target.parent / f".{staged.recipe.recipe}.git"
        shutil.rmtree(carried, ignore_errors=True)
        shutil.move(str(existing_git), str(carried))
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged.tree), str(target))
    if carried is not None:
        shutil.move(str(carried), str(target / ".git"))
    (target / STAGED).unlink(missing_ok=True)
    dump(staged.recipe, target)
    _commit(target, staged)
    echo(f"promoted → {target}")
    return target


def _commit(tree: Path, staged: Staged) -> None:
    """One commit per generation. Failures are non-fatal: the tree is still
    valid material, it just loses the diff between generations."""
    git = ["git", "-c", "user.email=chiron@localhost", "-c", "user.name=chiron"]
    try:
        if not (tree / ".git").is_dir():
            subprocess.run([*git, "-C", str(tree), "init", "-q"],
                           check=True, capture_output=True)
        subprocess.run([*git, "-C", str(tree), "add", "-A"],
                       check=True, capture_output=True)
        subprocess.run(
            [*git, "-C", str(tree), "commit", "-q", "--allow-empty", "-m",
             f"{staged.recipe.tool} @ {staged.recipe.source_commit or 'unknown'} "
             f"· {staged.pages} pages · {staged.digest[:12]}"],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, OSError):
        pass
