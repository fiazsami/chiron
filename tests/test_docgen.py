"""Generated documentation as corpus material.

The load-bearing claim of this feature is that a derived tree is just a
checkout: the adapter contract does not change, the manifest does not change,
and the viewer does not change. These tests hold that claim, and they hold the
one property everything else rests on — that generating twice produces the
same bytes, because every anchor is pinned to bytes.
"""

import json

import pytest

from tests.conftest import (
    APIDOC_ADAPTER, CODE_FILES, DERIVED_PAGES, git_commit_all, mount, run,
    write_derived, write_source,
)
from tools.lingua.corpora import CorpusError, discover, scan_corpus
from tools.lingua.docgen import TOOLS, recipe as recipe_mod
from tools.lingua.docgen.normalize import (
    first_difference, is_empty_page, normalize_text, normalize_tree, tree_digest,
)
from tools.lingua.docgen.probe import census
from tools.lingua.model import ScanError
from tools.lingua.translation import TranslationError, load_translation

SHA = "1" * 64
MINIMAL = {"recipe": "ts-public", "tool": "typedoc",
           "options": {"entry_points": ["src/index.ts"]}}


def _recipe(**over):
    return {**MINIMAL, **over}


# --- the recipe is a closed schema ------------------------------------------

@pytest.mark.parametrize("data, because", [
    (_recipe(tool="handwritten"), "the tool registry is closed"),
    (_recipe(recipe="Ts_Public"), "the slug names a directory"),
    ({"recipe": "x", "tool": "typedoc", "options": {}}, "entry_points is required"),
    (_recipe(options={"entry_points": ["a"], "verbosity": 3}), "unknown option key"),
    (_recipe(options={"entry_points": "src/index.ts"}), "list option given a string"),
    (_recipe(options={"entry_points": ["a"], "documented_only": "yes"}),
     "bool option given a string"),
    (_recipe(options={"entry_points": ["/etc/passwd"]}), "absolute path"),
    (_recipe(options={"entry_points": ["../../secrets"]}), "escapes the source"),
    (_recipe(image="ghcr.io/x/y:latest"), "a floating tag is not reproducible"),
    (_recipe(layout={"group_by": "vibes"}), "unknown grouping"),
    (_recipe(layout={"max_chapters": 10_000}), "over the authoring budget cap"),
    (_recipe(layout={"max_chapters": 0}), "under the budget floor"),
    (_recipe(layout={"depth": 2}), "unknown layout key"),
    (_recipe(schema=99), "a schema this chiron does not speak"),
])
def test_recipe_rejects(data, because):
    with pytest.raises(recipe_mod.RecipeError):
        recipe_mod.parse(data, "<test>")


def test_recipe_fills_defaults_without_mutating_the_spec():
    first = recipe_mod.parse(MINIMAL, "<test>")
    first.options["exclude"].append("**/*.test.ts")
    second = recipe_mod.parse(MINIMAL, "<test>")
    assert second.options["exclude"] == [], "defaults leaked between recipes"
    assert first.group_by == "directory" and first.max_chapters == 200


def test_recipe_round_trips_through_the_tree(tmp_path):
    parsed = recipe_mod.parse(
        _recipe(image=f"ghcr.io/x/y@sha256:{SHA}", source_commit="abc1234"), "<test>"
    )
    recipe_mod.dump(parsed, tmp_path)
    assert recipe_mod.load(tmp_path).to_dict() == parsed.to_dict()


def test_recipe_records_no_timestamp():
    """Generation time is not drift. If it were recorded it would be hashed."""
    blob = json.dumps(recipe_mod.parse(MINIMAL, "<t>").to_dict())
    assert "timestamp" not in blob and "generated_at" not in blob


# --- material: elects which tree a register scans ---------------------------

@pytest.mark.parametrize("value", [
    "derived/../../etc", "/etc", "source/../derived/x", "Derived/X", "derived/",
])
def test_translation_rejects_material_that_could_escape(tmp_path, value):
    (tmp_path / "translation.yaml").write_text(
        f"modes: [lexicon]\nmaterial: {value}\n"
    )
    with pytest.raises(TranslationError):
        load_translation(tmp_path, "<test>")


def test_material_defaults_to_source(markdown_corpus):
    corpora, source = markdown_corpus
    cfg = discover(corpora)[0][0]
    assert cfg.material is None
    assert cfg.source_dir == corpora / "demo-course" / "source"


def test_material_points_the_adapter_at_the_derived_tree(derived_corpus):
    corpora, corpus_dir = derived_corpus
    cfg = discover(corpora)[0][0]
    assert cfg.source_dir == corpus_dir / "derived" / "ts-public"


def test_missing_derived_tree_names_the_command_that_makes_it(derived_corpus):
    corpora, corpus_dir = derived_corpus
    for path in sorted((corpus_dir / "derived" / "ts-public").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (corpus_dir / "derived" / "ts-public").rmdir()
    with pytest.raises(CorpusError, match="ch doc --stage"):
        discover(corpora)


def test_derived_tree_without_a_recipe_is_rejected(derived_corpus):
    corpora, corpus_dir = derived_corpus
    (corpus_dir / "derived" / "ts-public" / ".chiron" / "recipe.yaml").unlink()
    with pytest.raises(CorpusError, match="recipe.yaml"):
        discover(corpora)


def test_a_symlinked_derived_tree_is_refused(tmp_path, derived_corpus):
    """MATERIAL_RE cannot catch this one — only the resolved path can."""
    corpora, corpus_dir = derived_corpus
    elsewhere = tmp_path / "elsewhere"
    write_source(elsewhere, DERIVED_PAGES)
    (elsewhere / ".chiron").mkdir()
    (elsewhere / ".chiron" / "recipe.yaml").write_text("schema: 1\n")
    tree = corpus_dir / "derived" / "ts-public"
    for path in sorted(tree.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    tree.rmdir()
    tree.symlink_to(elsewhere)
    with pytest.raises(CorpusError, match="outside"):
        discover(corpora)


def test_source_may_still_be_a_symlink(markdown_corpus):
    """/ch:mount symlinks source/ for a local folder — never break that."""
    corpora, source = markdown_corpus
    assert (corpora / "demo-course" / "source").is_symlink()
    assert discover(corpora)[0][0].source_dir.is_dir()


# --- apidoc chapters a generated tree deterministically ---------------------

def test_apidoc_chaptering_is_stable_across_scans(derived_corpus):
    corpora, _ = derived_corpus
    cfg = discover(corpora)[0][0]
    first = [(c.local_id, c.content_hash, c.title) for c in scan_corpus(cfg).chapters]
    second = [(c.local_id, c.content_hash, c.title) for c in scan_corpus(cfg).chapters]
    assert first == second
    assert first, "the fixture tree produced no chapters"


def test_apidoc_titles_and_groups_come_from_the_tree(derived_corpus):
    corpora, _ = derived_corpus
    corpus = scan_corpus(discover(corpora)[0][0])
    assert [g.id for g in corpus.groups] == ["client", "reference", "runtime"]
    titles = {c.local_id: c.title for c in corpus.chapters}
    assert "BamlRuntime" in titles.values()
    # Loose top-level pages group as "reference"; "api" is a reserved id.
    assert any(c.group == "reference" for c in corpus.chapters)


def test_apidoc_links_back_to_the_upstream_file_not_the_generated_page(derived_corpus):
    corpora, _ = derived_corpus
    corpus = scan_corpus(discover(corpora)[0][0])
    runtime = next(c for c in corpus.chapters if c.title == "BamlRuntime")
    assert runtime.source_url.endswith("/blob/main/src/runtime/mod.ts#L42")


def test_apidoc_group_by_module_aggregates(derived_corpus):
    corpora, corpus_dir = derived_corpus
    per_page = len(scan_corpus(discover(corpora)[0][0]).chapters)
    (corpus_dir / "v1" / "translation.yaml").write_text(
        "modes: [lexicon]\nmaterial: derived/ts-public\n"
        "adapter:\n  group_by: module\n"
    )
    per_module = len(scan_corpus(discover(corpora)[0][0]).chapters)
    assert per_module < per_page


def test_apidoc_refuses_a_group_that_shadows_a_viewer_route(derived_corpus):
    corpora, corpus_dir = derived_corpus
    tree = corpus_dir / "derived" / "ts-public"
    (tree / "api").mkdir()
    (tree / "api" / "Thing.md").write_text("# Thing\n\nA thing.\n")
    with pytest.raises(ScanError, match="shadows viewer routes"):
        scan_corpus(discover(corpora)[0][0])


def test_max_chapters_is_an_authoring_budget(derived_corpus):
    corpora, corpus_dir = derived_corpus
    write_derived(corpus_dir, max_chapters=2)
    with pytest.raises(ScanError, match="budget"):
        scan_corpus(discover(corpora)[0][0])


def test_apidoc_rejects_unknown_adapter_options(derived_corpus):
    corpora, corpus_dir = derived_corpus
    (corpus_dir / "v1" / "translation.yaml").write_text(
        "modes: [lexicon]\nmaterial: derived/ts-public\nadapter:\n  depth: 2\n"
    )
    with pytest.raises(ScanError, match="unknown option"):
        scan_corpus(discover(corpora)[0][0])


# --- the contract with web/: nothing changes --------------------------------

def test_a_generated_register_builds_a_v6_manifest(derived_corpus, capsys):
    corpora, _ = derived_corpus
    code, _ = run(corpora, capsys=capsys)
    assert code == 0
    manifest = json.loads((corpora / ".manifest.json").read_text())
    assert manifest["version"] == 6, "the viewer pins version 6"
    entry = manifest["corpora"][0]
    assert entry["source_kind"] == "markdown", "generated material is Markdown"
    assert {c["kind"] for c in manifest["chapters"]} == {"doc"}


def test_generated_chapters_render_pages_like_any_other(derived_corpus, capsys):
    corpora, corpus_dir = derived_corpus
    run(corpora, capsys=capsys)
    pages = sorted((corpus_dir / "v1" / "pages").rglob("*.md"))
    assert pages, "no pages rendered"
    body = (corpus_dir / "v1" / "pages" / "runtime" / "bamlruntime.md").read_text()
    assert "content_hash:" in body and "kind: doc" in body


# --- determinism, the property everything rests on --------------------------

def test_normalize_strips_what_varies_with_the_run():
    raw = (
        "# Runtime\r\n\r\nReads `/src/pkg/runtime.ts` on 2024-03-01T12:00:00Z.   \r\n"
        "\r\n\r\n\r\nDetail.\r\n\r\n***\n"
        "Generated using [typedoc-plugin-markdown](https://x) and [TypeDoc](https://y)\n"
    )
    out = normalize_text(raw, TOOLS["typedoc"])
    assert "\r" not in out
    assert "/src/" not in out and "pkg/runtime.ts" in out
    assert "2024-03-01" not in out
    assert "TypeDoc" not in out
    assert "\n\n\n" not in out
    assert out == normalize_text(raw, TOOLS["typedoc"]), "not idempotent"


def test_normalize_is_idempotent_on_its_own_output():
    once = normalize_text("# A\n\nGenerated by Doxygen 1.9.8\n\ntext\n", TOOLS["doxygen"])
    assert normalize_text(once, TOOLS["doxygen"]) == once


def test_empty_pages_are_dropped_and_their_directories_pruned(tmp_path):
    write_source(tmp_path, {
        "mod/Real.md": "# Real\n\nHas prose.\n",
        "stub/Nav.md": "# Nav\n\n## Children\n",
    })
    normalized, dropped = normalize_tree(tmp_path, TOOLS["typedoc"])
    assert (normalized, dropped) == (1, 1)
    assert not (tmp_path / "stub").exists(), "emptied directory left behind"


def test_is_empty_page_keeps_anything_with_prose():
    assert is_empty_page("# Foo\n\n### Bar\n")
    assert not is_empty_page("# Foo\n\nA sentence.\n")


def test_tree_digest_tracks_content_not_generation(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_source(a, DERIVED_PAGES)
    write_source(b, DERIVED_PAGES)
    assert tree_digest(a) == tree_digest(b)
    assert first_difference(a, b) is None
    (b / "runtime" / "BamlRuntime.md").write_text("# BamlRuntime\n\nChanged.\n")
    assert tree_digest(a) != tree_digest(b)


def test_first_difference_names_the_file_and_line(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_source(a, {"m/X.md": "# X\n\nsame\ndiffers here\n"})
    write_source(b, {"m/X.md": "# X\n\nsame\nand here it does not\n"})
    found = first_difference(a, b)
    assert "m/X.md:4" in found and "differs between runs" in found


def test_first_difference_reports_a_missing_page(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_source(a, {"m/X.md": "# X\n\nprose\n", "m/Y.md": "# Y\n\nprose\n"})
    write_source(b, {"m/X.md": "# X\n\nprose\n"})
    assert "different files" in first_difference(a, b)


def test_the_recipe_is_excluded_from_the_digest(tmp_path):
    write_source(tmp_path, DERIVED_PAGES)
    before = tree_digest(tmp_path)
    (tmp_path / ".chiron").mkdir()
    (tmp_path / ".chiron" / "recipe.yaml").write_text("schema: 1\ndigest: whatever\n")
    assert tree_digest(tmp_path) == before, "the recipe cannot record its own digest"


# --- the census grounds tool selection --------------------------------------

def test_census_finds_candidates_and_manifests(tmp_path):
    write_source(tmp_path, CODE_FILES)
    result = census(tmp_path)
    assert [c.tool for c in result.candidates] == ["pydoc-markdown"]
    assert result.candidates[0].files == 5
    assert result.prose_files == 1


def test_census_measures_doc_comment_density(tmp_path):
    write_source(tmp_path, {
        "pkg/documented.py": '"""A module docstring."""\n\ndef f():\n    pass\n',
        "pkg/bare.py": "def g():\n    pass\n",
    })
    candidate = census(tmp_path).candidates[0]
    assert candidate.files == 2 and candidate.documented == 1
    assert candidate.density == pytest.approx(0.5)


def test_census_skips_vendored_trees(tmp_path):
    write_source(tmp_path, {
        "pkg/real.py": "def f():\n    pass\n",
        "node_modules/dep/index.js": "module.exports = 1\n",
        ".venv/lib/thing.py": "x = 1\n",
    })
    result = census(tmp_path)
    assert [c.tool for c in result.candidates] == ["pydoc-markdown"]
    assert result.candidates[0].files == 1


def test_census_publishes_the_closed_registry_to_its_reader(tmp_path):
    """The planner may only choose what the census printed."""
    write_source(tmp_path, CODE_FILES)
    from tools.lingua.docgen.probe import render
    text = render(census(tmp_path), "demo")
    assert "pydoc-markdown.packages" in text
    assert "required" in text
