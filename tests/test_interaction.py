"""The interaction language's own contract: one target grammar, one state
line, and a study path whose verdicts come from the substrate."""

import json

import pytest
from conftest import run

from tools.lingua import corpora as corporamod
from tools.lingua import study, where
from tools.lingua.corpora import CorpusError
from tools.lingua.resolve import GRAMMAR, resolve_targets
from tools.lingua.status import build_bundle
from tools.lingua.where import state_line


def bundle_for(reference_dir):
    configs, _ = corporamod.discover(reference_dir)
    corpus = corporamod.scan_corpus(configs[0])
    return build_bundle(corpus, configs[0].data_dir)


# --- one target grammar ------------------------------------------------------

@pytest.mark.parametrize("target", [
    "demo-course",
    "demo-course/v1",
    "demo-course/v1/foundations",
    "foundations/01",
    "demo-course/foundations/01",
    "demo-course/v1/foundations/01",
])
def test_every_documented_target_form_resolves(markdown_corpus, target):
    """Every form the grammar advertises resolves through one code path.
    Before this, three resolvers accepted three different subsets."""
    bundles = [bundle_for(markdown_corpus[0])]
    selections = resolve_targets(bundles, [target], pending_only=False)
    assert len(selections) == 1
    assert selections[0].chapters


def test_all_and_no_args_agree(markdown_corpus):
    bundles = [bundle_for(markdown_corpus[0])]
    everything = resolve_targets(bundles, ["all"], pending_only=False)
    default = resolve_targets(bundles, [], pending_only=False)
    assert [c.id for c in everything[0].chapters] == \
        [c.id for c in default[0].chapters]


def test_unknown_target_carries_the_grammar(markdown_corpus):
    bundles = [bundle_for(markdown_corpus[0])]
    with pytest.raises(CorpusError) as exc:
        resolve_targets(bundles, ["nope/99"])
    assert GRAMMAR in str(exc.value)


def test_resolve_command_reports_states(markdown_corpus, capsys):
    code, out = run(markdown_corpus[0], "resolve", "foundations/01",
                    capsys=capsys)
    assert code == 0
    assert "demo-course/v1/foundations/01" in out
    assert "lexicon none" in out


# --- one state line ----------------------------------------------------------

def test_one_state_line_everywhere(markdown_corpus, capsys):
    """`where`, `status` and `check` must print the byte-identical line —
    the whole point of generating it in one place."""
    reference_dir = markdown_corpus[0]
    canonical = state_line(bundle_for(reference_dir))

    _, where_out = run(reference_dir, "where", capsys=capsys)
    _, status_out = run(reference_dir, "status", capsys=capsys)
    _, check_out = run(reference_dir, "check", capsys=capsys)
    for out in (where_out, status_out, check_out):
        assert canonical in out


def test_state_line_ladder_ends_at_study(markdown_corpus, monkeypatch):
    """An unauthored register points at /ch:translate; a finished one points
    at /ch:calibrate. The last rung is the design in one string."""
    bundle = bundle_for(markdown_corpus[0])
    assert "/ch:translate" in where.next_action(bundle)

    monkeypatch.setattr(bundle, "chapter_states",
                        lambda chapter: {"lexicon": "ok"})
    assert where.next_action(bundle) == \
        "/ch:calibrate demo-course/v1"


def test_status_no_longer_hides_warnings(markdown_corpus, capsys):
    """status was the one command that hid what check reported — a
    half-finished mount was invisible from the orientation command."""
    (markdown_corpus[0] / "half-mounted").mkdir()
    _, out = run(markdown_corpus[0], "status", capsys=capsys)
    assert "half-mounted" in out
    assert "legend:" in out


def test_check_says_ok_when_clean(markdown_corpus, capsys):
    """Voice law 3: silence is never success."""
    bundle = bundle_for(markdown_corpus[0])
    empty = {"lexicon": "ok", "phrasebook": "ok", "concept-relations": "ok"}
    import tools.lingua.status as statusmod
    original = statusmod.RegisterBundle.chapter_states
    statusmod.RegisterBundle.chapter_states = lambda self, chapter: empty
    try:
        _, out = run(markdown_corpus[0], "check", capsys=capsys)
    finally:
        statusmod.RegisterBundle.chapter_states = original
    assert "ok — every tracked state is ok" in out


# --- study grades against the substrate, not an opinion ----------------------

def _seed_lexicon(reference_dir, capsys, tmp_path):
    payload = {"terms": [{
        "slug": "context-window", "define": True, "term": "context window",
        "kind": "concept", "definition": "The token budget for one call.",
        "aliases": ["ctx window"],
        "anchors": [{"chapter": "foundations/01",
                     "quote": "The context window holds everything the "
                              "model can see in one call"}],
    }]}
    path = tmp_path / "lex.json"
    path.write_text(json.dumps(payload))
    code, _ = run(reference_dir, "set", "lexicon", "foundations/01",
                  "--from", str(path), capsys=capsys)
    assert code == 0


def test_grade_lands_on_the_corpus_own_form(markdown_corpus, capsys, tmp_path):
    reference_dir = markdown_corpus[0]
    _seed_lexicon(reference_dir, capsys, tmp_path)
    code, out = run(reference_dir, "grade", "demo-course/v1", "--no-log",
                    "--text", "the context window", capsys=capsys)
    assert code == 0
    assert "verdict: lands" in out
    assert "term:context-window" in out


def test_grade_counts_drift_and_invents_nothing(markdown_corpus, capsys,
                                                tmp_path):
    """The anti-chatbot proof: an ungrounded instruction exits 1, and no
    corpus term is offered for a word the corpus does not name."""
    reference_dir = markdown_corpus[0]
    _seed_lexicon(reference_dir, capsys, tmp_path)
    code, out = run(reference_dir, "grade", "demo-course/v1", "--no-log",
                    "--text", "add a middleware to the dispatcher",
                    capsys=capsys)
    assert code == 1
    assert "verdict: drifts" in out
    assert "middleware" in out
    assert "term:middleware" not in out


def test_grade_reads_aliases(markdown_corpus, capsys, tmp_path):
    """aliases have been stored since day one and never read by anything."""
    reference_dir = markdown_corpus[0]
    _seed_lexicon(reference_dir, capsys, tmp_path)
    code, out = run(reference_dir, "grade", "demo-course/v1", "--no-log",
                    "--text", "the ctx window", capsys=capsys)
    assert code == 0
    assert "alias" in out


def test_drill_verdict_is_the_exit_code(markdown_corpus, capsys, tmp_path):
    reference_dir = markdown_corpus[0]
    _seed_lexicon(reference_dir, capsys, tmp_path)
    miss, out = run(reference_dir, "grade", "demo-course/v1", "--no-log",
                    "--against", "term:context-window",
                    "--text", "the prompt budget", capsys=capsys)
    assert miss == 1 and "verdict: miss" in out
    hit, out = run(reference_dir, "grade", "demo-course/v1", "--no-log",
                   "--against", "term:context-window",
                   "--text", "the context window", capsys=capsys)
    assert hit == 0 and "verdict: hit" in out


def test_ask_surfaces_the_drift_pin(markdown_corpus, capsys, tmp_path):
    """Provenance — the grounding story the methodology calls the point of
    the system — reaches a human surface for the first time here."""
    reference_dir = markdown_corpus[0]
    _seed_lexicon(reference_dir, capsys, tmp_path)
    bundle = bundle_for(reference_dir)
    pin = bundle.data["lexicon"]["context-window"]["anchors"][0]["curated_against"]
    code, out = run(reference_dir, "ask", "demo-course/v1", "context window",
                    capsys=capsys)
    assert code == 0
    assert f"@ {pin}" in out


def test_calibration_log_is_opt_out_and_under_work(markdown_corpus, capsys,
                                                   tmp_path):
    reference_dir = markdown_corpus[0]
    _seed_lexicon(reference_dir, capsys, tmp_path)
    bundle = bundle_for(reference_dir)
    log = study.calibration_log(bundle)
    run(reference_dir, "grade", "demo-course/v1", "--no-log",
        "--text", "the context window", capsys=capsys)
    assert not log.exists()
    run(reference_dir, "grade", "demo-course/v1",
        "--text", "the context window", capsys=capsys)
    assert log.exists()
    record = json.loads(log.read_text().splitlines()[0])
    assert record["verdict"] == "lands"
    assert "work" in str(log) and "data" not in log.parts[-2:]


# --- the gate shows its material ---------------------------------------------

def test_gate_material_and_both_branches(markdown_corpus, tmp_path, capsys):
    import json as _json

    from tools.lingua import author as authormod

    reference_dir = markdown_corpus[0]
    seed = tmp_path / "seed.json"
    seed.write_text(_json.dumps({"terms": [{
        "slug": "context-window", "define": True, "term": "context window",
        "kind": "concept", "definition": "The token budget for one call.",
        "anchors": [{"chapter": "foundations/01",
                     "quote": "The context window holds everything the model "
                              "can see in one call"}],
    }]}))
    assert run(reference_dir, "set", "lexicon", "foundations/01",
               "--from", str(seed), capsys=capsys)[0] == 0

    bundle = bundle_for(reference_dir)
    wd = authormod.work_dir(bundle)
    (wd / "results").mkdir(parents=True, exist_ok=True)
    chapter = next(c for c in bundle.corpus.chapters if c.local_id == "rag/01")
    key = authormod._key(chapter)
    (wd / "results" / f"{key}.json").write_text(_json.dumps({
        "redefinitions": [{"slug": "context-window",
                           "reason": "the rag chapter gives the fuller one"}],
        "lexicon": {"terms": [{
            "slug": "context-window", "define": True, "term": "context window",
            "kind": "concept", "definition": "Everything appended before a call.",
            "anchors": [{"chapter": "rag/01",
                         "quote": "appended to the prompt before the call"}],
        }]},
    }))
    (wd / "run.json").write_text(_json.dumps({
        "batch_id": None, "model": "m", "effort": "e",
        "chapters": {key: {"id": chapter.id, "modes": list(bundle.tracked_modes),
                           "attempts": 0, "parked": None}},
        "created_at": 0}))

    assert authormod.apply_results(bundle, check=False) == 0
    out = capsys.readouterr().out

    # Both sides of the decision, inline.
    assert "The token budget for one call." in out, "incumbent definition missing"
    assert "Everything appended before a call." in out, "proposed definition missing"
    # Each side's grounding — the actual argument.
    assert "evidence foundations/01" in out
    assert "evidence rag/01" in out
    # Both branches runnable; neither is a hand-edit.
    assert "accept:" in out and "--redefine" in out
    assert "reject:" in out and "demoted.json" in out
    # The reject branch is a file the CLI already wrote.
    demoted = wd / "gated" / f"{key}-lexicon.demoted.json"
    assert demoted.exists()
    assert _json.loads(demoted.read_text())["terms"][0]["define"] is False
    # And the cost of doing nothing is stated.
    assert "unapplied until you run the commands below" in out


def test_unanswerable_question_reports_a_substrate_gap(markdown_corpus, capsys,
                                                       tmp_path):
    """Study failure becomes a production action — the loop neither surface
    had. Nearest-neighbour search always returns neighbours, so this only
    works with a match floor."""
    reference_dir = markdown_corpus[0]
    _seed_lexicon(reference_dir, capsys, tmp_path)
    code, out = run(reference_dir, "ask", "demo-course/v1",
                    "kubernetes ingress controller", capsys=capsys)
    assert code == 1
    assert "substrate gap" in out
    assert "/ch:translate" in out
