"""Fixture builders: a tiny devenv written into tmp_path (never the repo tree).

Every fixture returns the *reference* room — the one discovery scans. The
devenv shell itself is exercised in test_devenv.py."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.lingua.__main__ import main as lingua_main  # noqa: E402

MARKDOWN_DOCS = {
    "foundations/01-context.md": (
        "# The Context Window\n\n"
        "The context window holds everything the model can see in one call, "
        "and the course sizes examples against it before retrieval is "
        "introduced.\n"
    ),
    "foundations/02-prompts.md": (
        "# Prompt Shapes\n\n"
        "A system prompt frames the task; few-shot examples calibrate the "
        "answer style.\n"
    ),
    "rag/01-chroma.md": (
        "# Chroma Basics\n\n"
        "chromadb.Client() keeps everything in memory; nothing persists "
        "between runs. Retrieved documents are appended to the prompt before "
        "the call.\n"
    ),
}

CODE_FILES = {
    "server/handlers/routes.py": (
        '"""Route table for the demo server."""\n\n'
        "def register_routes(app):\n"
        "    # every handler is registered against the shared route table\n"
        '    app.add("/health", health)\n'
    ),
    "server/handlers/util.py": (
        "def trim(value):\n    return value.strip()\n"
    ),
    "server/store/db.py": (
        "class Store:\n"
        '    """A tiny in-memory store keyed by collection name."""\n'
    ),
    "server/app.py": "def make_app():\n    return None\n",
    "cli/main.py": 'def main():\n    print("demo cli entry point")\n',
    "README.md": "# Demo Code\n\nA tiny undocumented service.\n",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def write_source(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def git_commit_all(root: Path, message: str = "commit") -> None:
    if not (root / ".git").exists():
        _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)


def reference_room(tmp_path: Path) -> Path:
    """The room discovery scans, laid out the way tools.lingua.devenv does."""
    reference = tmp_path / "devenv" / "reference"
    (tmp_path / "devenv" / "workspace").mkdir(parents=True)
    reference.mkdir(parents=True)
    return reference


def mount(reference_dir: Path, name: str, source: Path, translation: str,
          adapter: str, title: str = "Fixture") -> Path:
    corpus_dir = reference_dir / name
    (corpus_dir / "v1" / "tools").mkdir(parents=True)
    (corpus_dir / "source").symlink_to(source)
    (corpus_dir / "corpus.yaml").write_text(f"title: {title}\nurls:\n  repo: https://example.com/x\n")
    (corpus_dir / "v1" / "translation.yaml").write_text(translation)
    (corpus_dir / "v1" / "tools" / "adapter.py").write_text(adapter)
    return corpus_dir


MARKDOWN_ADAPTER = (
    "from tools.lingua.sources import markdown\n\n"
    "def scan(cfg, root):\n    return markdown.scan(cfg, root)\n"
)
CODETREE_ADAPTER = (
    "from tools.lingua.sources import codetree\n\n"
    "def scan(cfg, root):\n    return codetree.scan(cfg, root)\n"
)
APIDOC_ADAPTER = (
    "from tools.lingua.sources import apidoc\n\n"
    "def scan(cfg, root):\n    return apidoc.scan(cfg, root)\n"
)
ALL_MODES = "modes: [lexicon, phrasebook, concept-relations]\n"

# A derived tree as `ch doc --promote` leaves one: Markdown, plus the recipe
# that produced it. Two groups, one nested module, one "Defined in" pointer.
DERIVED_PAGES = {
    "index.md": "# API Reference\n\nThe public surface of the demo package.\n",
    "runtime/index.md": "# Runtime\n\nEverything that executes a compiled function.\n",
    "runtime/BamlRuntime.md": (
        "# BamlRuntime\n\nCompiles `.baml` sources into a typed client.\n\n"
        "**Defined in** src/runtime/mod.ts:42\n"
    ),
    "runtime/internals/Tracer.md": "# Tracer\n\nWalks the span tree.\n",
    "client/Collector.md": "# Collector\n\nGathers traces emitted during a call.\n",
}
DERIVED_RECIPE = """schema: 1
recipe: ts-public
tool: typedoc
image: ghcr.io/example/chiron-docgen@sha256:{sha}
source_commit: abc1234
options:
  entry_points: [src/index.ts]
  documented_only: true
layout:
  group_by: {group_by}
  max_chapters: {max_chapters}
determinism:
  verified: true
  digest: deadbeef
""".replace("{sha}", "1" * 64)


def write_derived(corpus_dir, recipe: str = "ts-public", *, group_by: str = "directory",
                  max_chapters: int = 50, pages: dict | None = None):
    """Materialize <reference>/<name>/derived/<recipe>/ the way promote does."""
    tree = corpus_dir / "derived" / recipe
    write_source(tree, pages if pages is not None else DERIVED_PAGES)
    (tree / ".chiron").mkdir(parents=True, exist_ok=True)
    (tree / ".chiron" / "recipe.yaml").write_text(
        DERIVED_RECIPE.format(group_by=group_by, max_chapters=max_chapters)
    )
    git_commit_all(tree, "generated")
    return tree


@pytest.fixture
def markdown_corpus(tmp_path):
    """(reference room, source dir) with a committed 3-chapter markdown corpus."""
    source = tmp_path / "src"
    write_source(source, MARKDOWN_DOCS)
    git_commit_all(source)
    reference = reference_room(tmp_path)
    mount(reference, "demo-course", source, ALL_MODES, MARKDOWN_ADAPTER)
    return reference, source


@pytest.fixture
def derived_corpus(tmp_path):
    """(reference room, corpus dir) with a register scanning a derived tree."""
    source = tmp_path / "src"
    write_source(source, CODE_FILES)
    git_commit_all(source)
    reference = reference_room(tmp_path)
    corpus_dir = mount(
        reference, "demo-api", source,
        "modes: [lexicon]\nmaterial: derived/ts-public\n", APIDOC_ADAPTER,
    )
    write_derived(corpus_dir)
    return reference, corpus_dir


@pytest.fixture
def code_corpus(tmp_path):
    """(reference room, source dir) with a committed code corpus."""
    source = tmp_path / "src"
    write_source(source, CODE_FILES)
    git_commit_all(source)
    reference = reference_room(tmp_path)
    mount(reference, "demo-code", source, "modes: [lexicon]\n", CODETREE_ADAPTER)
    return reference, source


def run(reference_dir: Path, *args: str, capsys=None) -> tuple[int, str]:
    """Run the CLI in-process; returns (exit code, stdout)."""
    code = lingua_main(list(args), reference_dir=reference_dir)
    out = capsys.readouterr().out if capsys else ""
    return code, out
