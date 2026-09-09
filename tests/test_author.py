"""Offline tests for the API-native authoring stage (no API calls)."""

import json

import yaml

from conftest import run

from tools.lingua import author as authormod
from tools.lingua import corpora as corporamod
from tools.lingua.status import build_bundle


def bundle_for(corpora_dir):
    configs, _ = corporamod.discover(corpora_dir)
    corpus = corporamod.scan_corpus(configs[0])
    return build_bundle(corpus, configs[0].data_dir)


def write_run(bundle, results: dict[str, dict]) -> None:
    """Fake a collected run: results keyed by register-local chapter id."""
    wd = authormod.work_dir(bundle)
    (wd / "results").mkdir(parents=True, exist_ok=True)
    by_local = {c.local_id: c for c in bundle.corpus.chapters}
    plan = {}
    for local, result in results.items():
        chapter = by_local[local]
        key = authormod._key(chapter)
        plan[key] = {"id": chapter.id, "modes": list(bundle.tracked_modes)}
        (wd / "results" / f"{key}.json").write_text(json.dumps(result))
    (wd / "run.json").write_text(json.dumps(
        {"batch_id": "batch_test", "model": "m", "effort": "e",
         "chapters": plan, "created_at": 0}))


LEX_01 = {"terms": [{
    "slug": "context-window", "define": True, "term": "context window",
    "kind": "concept", "definition": "The token budget for one call.",
    "anchors": [{"chapter": "foundations/01",
                 "quote": "The context window holds everything the model can see in one call"}],
}]}


def test_schema_requires_requested_dimensions():
    schema = authormod.result_schema(["lexicon", "phrasebook"])
    assert set(schema["required"]) == {"redefinitions", "lexicon", "phrasebook"}
    assert "concept-relations" not in schema["properties"]
    assert schema["additionalProperties"] is False


def test_prompt_split_is_cache_friendly(markdown_corpus):
    corpora_dir, _ = markdown_corpus
    bundle = bundle_for(corpora_dir)
    shared = authormod.shared_context(bundle)
    chapter = bundle.corpus.chapters[0]
    message = authormod.chapter_message(
        chapter, bundle, list(bundle.tracked_modes))
    # Run-stable material lives only in the shared block...
    assert "## Methodology: lexicon" in shared
    assert "## Lexicon slug index" in shared
    assert "## Methodology" not in message
    # ...and per-chapter material only in the chapter block.
    assert f"# Extract: {chapter.id}" in message
    assert "## Chapter content" in message
    assert "Task: author these dimensions" in message

    params = authormod.build_params(
        bundle, chapter, ["lexicon"], "claude-sonnet-5", "medium", shared)
    assert params["system"][1]["cache_control"] == {"type": "ephemeral"}
    assert params["output_config"]["effort"] == "medium"
    assert params["output_config"]["format"]["type"] == "json_schema"


def test_apply_results_end_to_end(markdown_corpus, capsys):
    corpora_dir, _ = markdown_corpus
    bundle = bundle_for(corpora_dir)
    results = {
        "foundations/01": {
            "redefinitions": [],
            "lexicon": LEX_01,
            "phrasebook": {"phrases": [{
                "slug": "size-against-the-window",
                "phrase": "size examples against the context window",
                "intent": "budget prompt content",
                "terms": ["context-window"],
                "anchors": [{"chapter": "foundations/01",
                             "quote": "sizes examples against it before retrieval"}],
            }]},
            "concept-relations": {"edges": []},
        },
        # rag/01 defines context-window too — the earlier chapter wins and
        # this define is demoted to a mention, anchors preserved.
        "rag/01": {
            "redefinitions": [],
            "lexicon": {"terms": [{
                "slug": "context-window", "define": True,
                "term": "context window", "kind": "concept",
                "definition": "A different definition that must be dropped.",
                "anchors": [{"chapter": "rag/01",
                             "quote": "appended to the prompt before the call"}],
            }]},
        },
    }
    # concept-relations payload with empty edges is invalid — drop it instead.
    del results["foundations/01"]["concept-relations"]
    write_run(bundle, results)

    code = authormod.apply_results(bundle, check=False)
    out = capsys.readouterr().out
    assert code == 0
    assert "auto-demoted: context-window" in out

    data = yaml.safe_load(
        (corpora_dir / "demo-course/v1/data/lexicon.yaml").read_text())
    entry = data["context-window"]
    assert entry["defined_in"] == "foundations/01"
    assert entry["definition"] == "The token budget for one call."
    assert {a["chapter"] for a in entry["anchors"]} == {"foundations/01", "rag/01"}
    phrases = yaml.safe_load(
        (corpora_dir / "demo-course/v1/data/phrasebook.yaml").read_text())
    assert "size-against-the-window" in phrases


def test_apply_holds_declared_redefinitions(markdown_corpus, tmp_path, capsys):
    corpora_dir, _ = markdown_corpus
    # Seed ownership: foundations/01 defines context-window via set.
    payload_file = tmp_path / "seed.json"
    payload_file.write_text(json.dumps(LEX_01))
    code, _ = run(corpora_dir, "set", "lexicon", "foundations/01",
                  "--from", str(payload_file))
    assert code == 0

    bundle = bundle_for(corpora_dir)
    write_run(bundle, {
        "rag/01": {
            "redefinitions": [{"slug": "context-window",
                               "reason": "rag chapter gives the fuller definition"}],
            "lexicon": {"terms": [{
                "slug": "context-window", "define": True,
                "term": "context window", "kind": "concept",
                "definition": "Redefined from rag.",
                "anchors": [{"chapter": "rag/01",
                             "quote": "appended to the prompt before the call"}],
            }]},
        },
    })
    code = authormod.apply_results(bundle, check=False)
    out = capsys.readouterr().out
    assert code == 0
    assert "HELD for the redefinition gate" in out
    assert "--redefine" in out
    # Nothing was written for the gated chapter.
    data = yaml.safe_load(
        (corpora_dir / "demo-course/v1/data/lexicon.yaml").read_text())
    assert data["context-window"]["definition"] == "The token budget for one call."


def test_apply_rejects_ungrounded_and_records_failure(markdown_corpus, capsys):
    corpora_dir, _ = markdown_corpus
    bundle = bundle_for(corpora_dir)
    write_run(bundle, {
        "foundations/01": {
            "redefinitions": [],
            "lexicon": {"terms": [{
                "slug": "ghost", "define": True, "term": "ghost",
                "kind": "concept", "definition": "Not in the chapter.",
                "anchors": [{"chapter": "foundations/01",
                             "quote": "this sentence appears nowhere at all"}],
            }]},
        },
    })
    code = authormod.apply_results(bundle, check=False)
    out = capsys.readouterr().out
    assert code == 1
    assert "REJECTED foundations/01 lexicon" in out
    failures = json.loads(
        (authormod.work_dir(bundle) / "failures.json").read_text())
    assert "foundations/01" in failures


def test_apply_check_writes_nothing(markdown_corpus, capsys):
    corpora_dir, _ = markdown_corpus
    bundle = bundle_for(corpora_dir)
    write_run(bundle, {"foundations/01": {"redefinitions": [], "lexicon": LEX_01}})
    code = authormod.apply_results(bundle, check=True)
    out = capsys.readouterr().out
    assert code == 0
    assert "would apply" in out
    assert not (corpora_dir / "demo-course/v1/data/lexicon.yaml").exists()


def test_schema_strips_unsupported_constraint_keywords():
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in authormod._UNSUPPORTED_KEYS
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(authormod.result_schema(["lexicon", "phrasebook", "concept-relations"]))


def test_normalize_relocates_wrong_path(code_corpus, capsys):
    """An anchor whose declared path is a real unit file that lacks the
    quote is re-anchored to the unit file containing it."""
    corpora_dir, _ = code_corpus
    bundle = bundle_for(corpora_dir)
    write_run(bundle, {
        "server/01": {
            "redefinitions": [],
            "lexicon": {"terms": [{
                "slug": "route-table", "define": True, "term": "route table",
                "kind": "concept",
                "definition": "The shared registry handlers register against.",
                "anchors": [{
                    "chapter": "server/01",
                    "path": "server/handlers/util.py",  # real file, wrong one
                    "quote": "every   handler is registered\nagainst the shared route table",
                }],
            }]},
        },
    })
    code = authormod.apply_results(bundle, check=False)
    capsys.readouterr()
    assert code == 0
    data = yaml.safe_load(
        (corpora_dir / "demo-code/v1/data/lexicon.yaml").read_text())
    anchor = data["route-table"]["anchors"][0]
    assert anchor["path"] == "server/handlers/routes.py"
    # Quote stored whitespace-normalized — the grounding equivalence.
    assert anchor["quote"] == (
        "every handler is registered against the shared route table")
