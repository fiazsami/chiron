"""`ch doc` — get generated material onto disk.

Dispatched before the pipeline discovers registers, because this verb runs
during a mount: the corpus may have no register yet, and a register whose
`material:` names a tree that does not exist yet must not make discovery fail
before the command that creates it can run.

Every write here is gated at the skill layer. The CLI's job is to be the
single writer and to refuse anything it cannot account for.
"""

import sys
from pathlib import Path

from ..corpora import CorpusConfig
from ..gittree import source_version
from ..model import ScanError
from ..sources import apidoc
from ..where import cmd
from . import TOOLS
from .normalize import tree_digest
from .probe import census, render, render_json
from .recipe import RecipeError, load, load_json
from .runner import DockerError, generate
from .stage import Staged, promote, stage, staged_recipe, staging_dir


def add_parser(sub) -> None:
    doc = sub.add_parser(
        "doc",
        help="generate documentation from a corpus's code and mount it as "
             "material: --census to see what a generator would find, --stage "
             "to build and prove one, --promote to keep it. Needs Docker; "
             "nothing else in chiron does",
    )
    doc.add_argument("target", nargs="?", metavar="CORPUS",
                     help="a corpus name, or <corpus>/<recipe> for --promote/--clean")
    mode = doc.add_mutually_exclusive_group()
    mode.add_argument("--census", action="store_true",
                      help="what a generator would find here (writes nothing)")
    mode.add_argument("--stage", action="store_true",
                      help="generate into devenv/reference/<name>/.staging/<recipe>/ and "
                           "prove the result is deterministic")
    mode.add_argument("--promote", action="store_true",
                      help="move a proved staging tree into derived/<recipe>/")
    mode.add_argument("--status", action="store_true",
                      help="every derived tree: recipe, image, and whether it "
                           "is behind its source (writes nothing)")
    mode.add_argument("--clean", action="store_true",
                      help="delete a staging tree")
    doc.add_argument("--from", dest="from_file", metavar="FILE",
                     help="recipe JSON for --stage")
    doc.add_argument("--json", action="store_true", help="machine-readable census")


def project(tree: Path, corpus_dir: Path) -> str:
    """The chaptering this tree would produce, run through the real adapter.

    GATE M has to show the chapter count before anything is promoted, and the
    count is what the next authoring run will cost. Computing it any other way
    would be showing the user a different number from the one they get.
    """
    cfg = CorpusConfig(
        name=corpus_dir.name, register="v?", corpus_dir=corpus_dir, dir=tree,
        title=corpus_dir.name, urls={}, origin=None, label=None, modes=[],
        translation_notes=None, groups=None,
    )
    try:
        corpus = apidoc.scan(cfg, tree)
    except ScanError as exc:
        return f"  chaptering    WOULD FAIL — {exc}"
    by_group: dict[str, list] = {}
    for chapter in corpus.chapters:
        by_group.setdefault(chapter.group_label, []).append(chapter)
    lines = [f"  chapters      {len(corpus.chapters)} in "
             f"{len(by_group)} group(s)"]
    for label, chapters in by_group.items():
        titles = ", ".join(c.title for c in chapters[:4])
        more = f", … (+{len(chapters) - 4})" if len(chapters) > 4 else ""
        lines.append(f"    {label:<22} {len(chapters):>3}  {titles}{more}")
    return "\n".join(lines)


def _corpus_dir(reference_dir: Path, target: str | None) -> Path:
    if not target:
        raise ValueError(
            f"name a corpus: {cmd('doc --census <corpus>')}"
        )
    name = target.split("/")[0]
    path = reference_dir / name
    if not path.is_dir():
        mounted = sorted(p.name for p in reference_dir.iterdir()
                         if p.is_dir() and not p.name.startswith(".")) \
            if reference_dir.is_dir() else []
        raise ValueError(
            f"no corpus {name!r} under {reference_dir}"
            + (f" — mounted: {', '.join(mounted)}" if mounted else
               " — mount one with /ch:mount <url>")
        )
    return path


def _source(corpus_dir: Path) -> Path:
    source = corpus_dir / "source"
    if not source.is_dir():
        raise ValueError(
            f"{corpus_dir.name} has no source/ — finish the mount first "
            f"(/ch:mount)"
        )
    return source


def run_census(corpus_dir: Path, as_json: bool) -> int:
    result = census(_source(corpus_dir))
    if as_json:
        print(render_json(result))
        return 0
    print(render(result, corpus_dir.name))
    print()
    if not result.candidates:
        print("no generator serves this tree — mount against source/ instead")
        return 0
    if result.prose_ratio > 0.5:
        # Worth saying plainly: generating docs for an already-documented repo
        # buys scaffolding, not working language.
        print(f"note: this corpus is already {result.prose_ratio:.0%} prose. "
              f"Generated API docs would add scaffolding, not vocabulary — "
              f"mounting against source/ is likely the better register.")
        print()
    print(f"next: write a recipe, then "
          f"{cmd(f'doc --stage {corpus_dir.name} --from <recipe.json>')}")
    return 0


def run_stage(corpus_dir: Path, from_file: str | None) -> int:
    if not from_file:
        raise ValueError(
            f"--stage needs a recipe: "
            f"{cmd(f'doc --stage {corpus_dir.name} --from <recipe.json>')}"
        )
    recipe = load_json(Path(from_file))
    source = _source(corpus_dir)
    recipe.source_commit = source_version(source)
    print(f"staging {corpus_dir.name}/{recipe.recipe} · {recipe.tool}")
    # generate() pins the image onto the recipe as it runs.
    staged = stage(recipe, corpus_dir, generate=generate)
    print(f"  image         {staged.recipe.image}")

    if not staged.ok:
        print()
        print(f"FAILED — {recipe.tool} is not deterministic on this corpus.")
        print(f"  {staged.difference}")
        print()
        print("Every anchor is pinned to its chapter's content_hash, so a tree "
              "whose bytes\nmove on their own would mark the whole register "
              "stale on every regeneration.\nNot promoting it.")
        print()
        print(f"next: narrow the recipe and re-stage, or "
              f"{cmd(f'doc --clean {corpus_dir.name}/{recipe.recipe}')}")
        return 2

    tree = staged.tree
    print()
    print(f"staged  {tree}")
    print(f"  pages         {staged.pages}"
          + (f" ({staged.dropped} empty dropped)" if staged.dropped else ""))
    print(f"  digest        {staged.digest[:12]}")
    print(f"  proved        "
          + ("this run — two generations matched" if staged.proved
             else "previously; recorded in the recipe"))
    print(project(tree, corpus_dir))
    sample = sorted(tree.rglob("*.md"))[:1]
    if sample:
        print(f"  sample        {sample[0].relative_to(tree)}")
    print()
    print("Show GATE M the census, the recipe, the image, the determinism "
          "result,\nthe chaptering above, and one staged page in full.")
    print(f"next: {cmd(f'doc --promote {corpus_dir.name}/{recipe.recipe}')}")
    return 0


def run_promote(corpus_dir: Path, target: str) -> int:
    parts = target.split("/", 1)
    if len(parts) != 2:
        raise ValueError(
            f"name the recipe: {cmd(f'doc --promote {corpus_dir.name}/<recipe>')}"
        )
    slug = parts[1]
    tree = staging_dir(corpus_dir, slug)
    if not tree.is_dir():
        raise ValueError(
            f"nothing staged at {tree} — "
            f"{cmd(f'doc --stage {corpus_dir.name} --from <recipe.json>')} first"
        )
    try:
        recipe = staged_recipe(tree)
    except RecipeError as exc:
        raise ValueError(
            f"{tree} has no readable staged recipe ({exc}) — re-stage it; a "
            f"tree chiron cannot account for is not material"
        ) from exc
    if not recipe.verified:
        raise ValueError(
            f"{slug} has not proved deterministic — re-stage it. Promoting an "
            f"unproved tree would put drift into the state model."
        )
    staged = Staged(tree, recipe, pages=len(list(tree.rglob("*.md"))),
                    dropped=0, digest=tree_digest(tree), proved=False)
    target_dir = promote(staged, corpus_dir)
    print(f"  recipe   {target_dir}/.chiron/recipe.yaml")
    print()
    print(f"next: point a register at it — `material: derived/{slug}` in its "
          f"translation.yaml — then {cmd('')}".rstrip())
    return 0


def run_status(reference_dir: Path, target: str | None) -> int:
    corpus_dirs = (
        [_corpus_dir(reference_dir, target)] if target
        else sorted(p for p in reference_dir.iterdir()
                    if p.is_dir() and not p.name.startswith("."))
        if reference_dir.is_dir() else []
    )
    rows, behind = [], 0
    for corpus_dir in corpus_dirs:
        derived_root = corpus_dir / "derived"
        if not derived_root.is_dir():
            continue
        head = source_version(corpus_dir / "source")
        for tree in sorted(p for p in derived_root.iterdir() if p.is_dir()):
            try:
                recipe = load(tree)
            except RecipeError as exc:
                rows.append((f"{corpus_dir.name}/{tree.name}", "BROKEN", str(exc)[:60]))
                behind += 1
                continue
            stale = head != "unknown" and recipe.source_commit not in (None, head)
            behind += stale
            rows.append((
                f"{corpus_dir.name}/{tree.name}",
                "behind" if stale else "current",
                f"{recipe.tool} · generated from {recipe.source_commit or '?'}"
                + (f", source is at {head}" if stale else ""),
            ))
    if not rows:
        print(f"no derived trees. {cmd('doc --census <corpus>')} to see "
              f"whether one would help.")
        return 0
    width = max(len(r[0]) for r in rows)
    for name, state, detail in rows:
        print(f"{name:<{width}}  {state:<8} {detail}")
    print()
    if behind:
        print(f"{behind} derived tree(s) no longer match their source. Their "
              f"chapters still read `ok`\nbecause content_hash only knows the "
              f"generated bytes — regenerate to see the real drift:")
        print(f"  {cmd('doc --stage <corpus> --from <recipe.json>')}")
        return 1
    print("every derived tree matches the source it was generated from.")
    return 0


def run_clean(corpus_dir: Path, target: str) -> int:
    import shutil
    parts = target.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"name the recipe: {cmd(f'doc --clean {corpus_dir.name}/<recipe>')}")
    tree = staging_dir(corpus_dir, parts[1])
    if not tree.is_dir():
        print(f"nothing staged at {tree}")
        return 0
    shutil.rmtree(tree)
    print(f"removed {tree}")
    return 0


def dispatch(args, reference_dir: Path) -> int:
    """Run one `ch doc` command. Returns the process exit code."""
    try:
        if args.status:
            return run_status(reference_dir, args.target)
        corpus_dir = _corpus_dir(reference_dir, args.target)
        if args.census:
            return run_census(corpus_dir, args.json)
        if args.stage:
            return run_stage(corpus_dir, args.from_file)
        if args.promote:
            return run_promote(corpus_dir, args.target)
        if args.clean:
            return run_clean(corpus_dir, args.target)
        return run_census(corpus_dir, args.json)
    except (ValueError, RecipeError, DockerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
