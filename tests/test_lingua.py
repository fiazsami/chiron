"""End-to-end and validation tests for the tools.lingua pipeline."""

import json

import pytest
import yaml

from conftest import (
    ALL_MODES, CODETREE_ADAPTER, MARKDOWN_ADAPTER, git_commit_all, mount, run,
    write_source,
)

LEX_PAYLOAD = {
    "terms": [
        {
            "slug": "context-window", "define": True, "term": "context window",
            "kind": "concept",
            "definition": "The token budget holding everything the model can see.",
            "aliases": ["ctx window"],
            "anchors": [{
                "chapter": "foundations/01",
                "quote": "The context window holds everything the model can see in one call",
            }],
        },
    ]
}


def set_payload(tmp_path, corpora, dimension, chapter, payload, *extra):
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload))
    return run(corpora, "set", dimension, chapter, "--from", str(payload_file), *extra)


# --- discovery -------------------------------------------------------------

def test_discovery_warns_on_incomplete_mounts(tmp_path, capsys):
    corpora = tmp_path / "corpora"
    (corpora / "half-mounted").mkdir(parents=True)
    code, _ = run(corpora, "check")
    out = capsys.readouterr().out
    assert code == 0
    assert "no corpora mounted" in out


def test_reserved_group_id_rejected(tmp_path, capsys):
    source = tmp_path / "src"
    write_source(source, {"lexicon/01-x.md": "# X\n\nBody.\n"})
    git_commit_all(source)
    corpora = tmp_path / "corpora"
    corpora.mkdir()
    mount(corpora, "demo", source, ALL_MODES, MARKDOWN_ADAPTER)
    code, _ = run(corpora, "status")
    err = capsys.readouterr().err
    assert code == 2
    assert "reserved" in err


# --- validation ------------------------------------------------------------

def test_ungrounded_quote_rejected(tmp_path, markdown_corpus, capsys):
    corpora, _ = markdown_corpus
    payload = {"terms": [{
        "slug": "context-window", "define": True, "term": "context window",
        "kind": "concept", "definition": "A definition.",
        "anchors": [{"chapter": "foundations/01", "quote": "this is not in the chapter"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "lexicon", "foundations/01", payload)
    err = capsys.readouterr().err
    assert code == 2
    assert "quote not found" in err


def test_validation_lists_every_problem(tmp_path, markdown_corpus, capsys):
    corpora, _ = markdown_corpus
    payload = {"terms": [{
        "slug": "Bad Slug", "define": True, "kind": "nope",
        "anchors": [{"chapter": "wrong/99", "quote": "short"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "lexicon", "foundations/01", payload)
    err = capsys.readouterr().err
    assert code == 2
    for fragment in ("'slug' must match", "'term' is required", "'kind' must be one of",
                     "'definition' is required", "'chapter' must be the target"):
        assert fragment in err


def test_anchor_chapter_must_match_target(tmp_path, markdown_corpus, capsys):
    corpora, _ = markdown_corpus
    payload = {"terms": [{
        "slug": "x", "define": True, "term": "x", "kind": "concept",
        "definition": "d.",
        "anchors": [{"chapter": "rag/01", "quote": "chromadb.Client() keeps everything"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "lexicon", "foundations/01", payload)
    assert code == 2


def test_phrasebook_requires_lexicon_terms(tmp_path, markdown_corpus, capsys):
    corpora, _ = markdown_corpus
    payload = {"phrases": [{
        "slug": "p", "phrase": "say the thing", "intent": "test",
        "terms": ["missing-term"],
        "anchors": [{"chapter": "rag/01", "quote": "appended to the prompt"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "phrasebook", "rag/01", payload)
    err = capsys.readouterr().err
    assert code == 2
    assert "not in the lexicon" in err


def test_relations_require_lexicon_endpoints_and_known_type(tmp_path, markdown_corpus, capsys):
    corpora, _ = markdown_corpus
    payload = {"edges": [{
        "from": "nope", "to": "also-nope", "type": "banana", "gloss": "g.",
        "anchors": [{"chapter": "rag/01", "quote": "appended to the prompt"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "concept-relations", "rag/01", payload)
    err = capsys.readouterr().err
    assert code == 2
    assert "'type' must be one of" in err
    assert "not in the lexicon" in err


def test_untracked_mode_rejected(tmp_path, code_corpus, capsys):
    corpora, _ = code_corpus  # register enables lexicon only
    payload = {"phrases": []}
    code, _ = set_payload(tmp_path, corpora, "phrasebook", "cli/01", payload)
    err = capsys.readouterr().err
    assert code == 2
    assert "does not enable mode" in err


# --- define / redefine -----------------------------------------------------

def test_define_and_mention_and_redefine_gate(tmp_path, markdown_corpus, capsys):
    corpora, _ = markdown_corpus
    code, _ = set_payload(tmp_path, corpora, "lexicon", "foundations/01", LEX_PAYLOAD)
    assert code == 0

    mention = {"terms": [{
        "slug": "context-window", "define": False,
        "anchors": [{"chapter": "rag/01", "quote": "appended to the prompt before the call"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "lexicon", "rag/01", mention)
    assert code == 0
    data = yaml.safe_load(
        (corpora / "demo-course/v1/data/lexicon.yaml").read_text())
    assert data["context-window"]["defined_in"] == "foundations/01"
    assert {a["chapter"] for a in data["context-window"]["anchors"]} == {
        "foundations/01", "rag/01"}

    redefine = {"terms": [{
        "slug": "context-window", "define": True, "term": "context window",
        "kind": "concept", "definition": "A different definition.",
        "anchors": [{"chapter": "rag/01", "quote": "appended to the prompt before the call"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "lexicon", "rag/01", redefine)
    err = capsys.readouterr().err
    assert code == 2 and "--redefine" in err

    code, _ = set_payload(tmp_path, corpora, "lexicon", "rag/01", redefine, "--redefine")
    assert code == 0
    data = yaml.safe_load(
        (corpora / "demo-course/v1/data/lexicon.yaml").read_text())
    assert data["context-window"]["defined_in"] == "rag/01"
    # foundations/01's anchor survives the redefinition.
    assert {a["chapter"] for a in data["context-window"]["anchors"]} == {
        "foundations/01", "rag/01"}


def test_reauthoring_drops_abandoned_entries(tmp_path, markdown_corpus):
    corpora, _ = markdown_corpus
    set_payload(tmp_path, corpora, "lexicon", "foundations/01", LEX_PAYLOAD)
    replacement = {"terms": [{
        "slug": "sizing", "define": True, "term": "sizing", "kind": "concept",
        "definition": "Sizing examples against the window.",
        "anchors": [{"chapter": "foundations/01",
                     "quote": "sizes examples against it before retrieval"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "lexicon", "foundations/01", replacement)
    assert code == 0
    data = yaml.safe_load(
        (corpora / "demo-course/v1/data/lexicon.yaml").read_text())
    # context-window lost its only anchor -> dropped; sizing replaced it.
    assert set(data) == {"sizing"}


# --- drift -----------------------------------------------------------------

def test_drift_and_accept_drift(tmp_path, markdown_corpus, capsys):
    corpora, source = markdown_corpus
    set_payload(tmp_path, corpora, "lexicon", "foundations/01", LEX_PAYLOAD)

    doc = source / "foundations/01-context.md"
    doc.write_text(doc.read_text() + "\nNew sentence.\n")
    git_commit_all(source, "change")

    capsys.readouterr()
    code, _ = run(corpora, "status", "--json")
    out = json.loads(capsys.readouterr().out)
    states = {c["id"]: c["states"] for c in out["chapters"]}
    assert states["demo-course/v1/foundations/01"]["lexicon"] == "stale"

    code, _ = run(corpora, "accept-drift", "foundations/01", "--mode", "lexicon")
    assert code == 0
    capsys.readouterr()
    run(corpora, "status", "--json")
    out = json.loads(capsys.readouterr().out)
    states = {c["id"]: c["states"] for c in out["chapters"]}
    assert states["demo-course/v1/foundations/01"]["lexicon"] == "ok"


def test_uncommitted_source_change_does_not_drift(tmp_path, markdown_corpus, capsys):
    corpora, source = markdown_corpus
    set_payload(tmp_path, corpora, "lexicon", "foundations/01", LEX_PAYLOAD)
    doc = source / "foundations/01-context.md"
    doc.write_text(doc.read_text() + "\nUncommitted.\n")

    capsys.readouterr()
    run(corpora, "status", "--json")
    out = json.loads(capsys.readouterr().out)
    states = {c["id"]: c["states"] for c in out["chapters"]}
    assert states["demo-course/v1/foundations/01"]["lexicon"] == "ok"


def test_dangling_relation_endpoint_marks_stale(tmp_path, markdown_corpus, capsys):
    corpora, _ = markdown_corpus
    set_payload(tmp_path, corpora, "lexicon", "foundations/01", LEX_PAYLOAD)
    other = {"terms": [{
        "slug": "retrieval", "define": True, "term": "retrieval", "kind": "concept",
        "definition": "Fetching documents for the prompt.",
        "anchors": [{"chapter": "rag/01",
                     "quote": "Retrieved documents are appended to the prompt"}],
    }]}
    set_payload(tmp_path, corpora, "lexicon", "rag/01", other)
    edge = {"edges": [{
        "from": "retrieval", "to": "context-window", "type": "feeds",
        "gloss": "chunks are packed into the window",
        "anchors": [{"chapter": "rag/01", "quote": "appended to the prompt before the call"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "concept-relations", "rag/01", edge)
    assert code == 0

    # Re-author foundations/01 without context-window -> endpoint vanishes.
    replacement = {"terms": [{
        "slug": "sizing", "define": True, "term": "sizing", "kind": "concept",
        "definition": "Sizing examples.",
        "anchors": [{"chapter": "foundations/01",
                     "quote": "sizes examples against it"}],
    }]}
    set_payload(tmp_path, corpora, "lexicon", "foundations/01", replacement)
    capsys.readouterr()
    run(corpora, "status", "--json")
    out = json.loads(capsys.readouterr().out)
    states = {c["id"]: c["states"] for c in out["chapters"]}
    assert states["demo-course/v1/rag/01"]["concept-relations"] == "stale"


# --- build / manifest / sweep ---------------------------------------------

def test_build_manifest_and_sweep(tmp_path, markdown_corpus, capsys):
    corpora, source = markdown_corpus
    set_payload(tmp_path, corpora, "lexicon", "foundations/01", LEX_PAYLOAD)
    code, _ = run(corpora, "build")
    assert code == 0
    capsys.readouterr()

    manifest = json.loads((corpora / ".manifest.json").read_text())
    assert manifest["version"] == 6
    corpus = manifest["corpora"][0]
    assert corpus["source_kind"] == "markdown"
    assert corpus["modes"] == ["lexicon", "phrasebook", "concept-relations"]
    assert corpus["data"]["lexicon"]["path"] == "demo-course/v1/data/lexicon.yaml"
    assert corpus["pages"]["concept-relations"] == "demo-course/v1/pages/relations.md"
    assert corpus["totals"] == {"terms": 1, "phrases": 0, "relations": 0}
    chapter = next(c for c in manifest["chapters"]
                   if c["id"] == "demo-course/v1/foundations/01")
    assert chapter["terms_defined"] == ["context-window"]
    assert chapter["states"]["lexicon"] == "ok"
    assert chapter["kind"] == "doc"
    assert chapter["source_paths"] == ["foundations/01-context.md"]
    assert (corpora / chapter["page"]).exists()
    assert (corpora / "demo-course/v1/pages/lexicon.md").exists()

    # A removed chapter's page is swept on the next build.
    (source / "rag/01-chroma.md").unlink()
    git_commit_all(source, "remove chapter")
    stale_page = corpora / "demo-course/v1/pages/rag/01-chroma.md"
    assert stale_page.exists()
    run(corpora, "build")
    assert not stale_page.exists()
    assert not stale_page.parent.exists()  # emptied group dir pruned


def test_check_strict_exit_codes(tmp_path, markdown_corpus, capsys):
    corpora, _ = markdown_corpus
    code, _ = run(corpora, "check", "--strict")
    assert code == 1  # everything none
    capsys.readouterr()
    code, _ = run(corpora, "check")
    assert code == 0  # non-strict never fails on states


# --- codetree adapter ------------------------------------------------------

def test_codetree_grouping_and_hash_stability(tmp_path, code_corpus, capsys):
    corpora, _ = code_corpus
    run(corpora, "status", "--json")
    out = json.loads(capsys.readouterr().out)
    ids = {c["id"] for c in out["chapters"]}
    assert ids == {
        "demo-code/v1/server/01",  # handlers/
        "demo-code/v1/server/02",  # store/
        "demo-code/v1/server/03",  # server-files (app.py)
        "demo-code/v1/cli/01",
        "demo-code/v1/root/01",    # loose README.md
    }
    assert all(c["kind"] == "code" for c in out["chapters"])
    hashes = {c["id"]: c["content_hash"] for c in out["chapters"]}

    run(corpora, "status", "--json")
    out2 = json.loads(capsys.readouterr().out)
    assert hashes == {c["id"]: c["content_hash"] for c in out2["chapters"]}


def test_codetree_grounded_set_with_path(tmp_path, code_corpus, capsys):
    corpora, _ = code_corpus
    payload = {"terms": [{
        "slug": "route-table", "define": True, "term": "route table",
        "kind": "concept",
        "definition": "The shared registry every handler is registered against.",
        "anchors": [{"chapter": "server/01", "path": "server/handlers/routes.py",
                     "quote": "every handler is registered against the shared route table"}],
    }]}
    code, _ = set_payload(tmp_path, corpora, "lexicon", "server/01", payload)
    assert code == 0

    # path is required for code chapters
    payload["terms"][0]["anchors"][0].pop("path")
    code, _ = set_payload(tmp_path, corpora, "lexicon", "server/01", payload)
    err = capsys.readouterr().err
    assert code == 2
    assert "'path' is required for code chapters" in err


# --- extract ---------------------------------------------------------------

def test_extract_bundle_headings(tmp_path, markdown_corpus, capsys):
    corpora, _ = markdown_corpus
    set_payload(tmp_path, corpora, "lexicon", "foundations/01", LEX_PAYLOAD)
    capsys.readouterr()
    code, _ = run(corpora, "extract", "foundations/01")
    out = capsys.readouterr().out
    assert code == 0
    for heading in (
        "# Extract: demo-course/v1/foundations/01",
        "## Translation requirements (register v1)",
        "## Methodology: lexicon",
        "## Chapter content",
        "## Current lexicon entries anchored here",
        "## Lexicon slug index",
        "<<<BEGIN slug-index>>>",
    ):
        assert heading in out
    assert "context-window: context window (concept)" in out
