"""The development environment's own contract: two rooms, declared and checked.

The layout used to be a string in __main__; nothing could tell a corpus in the
right room from one dropped beside it. These tests are what "enforced via
configuration" means — a config that is validated rather than trusted, rooms
that cannot escape the root, discovery confined to `reference`, and a legacy
tree that stops the CLI rather than half-working.
"""

import pytest
from conftest import ALL_MODES, MARKDOWN_ADAPTER, MARKDOWN_DOCS, git_commit_all, mount, write_source

from tools.lingua import devenv
from tools.lingua.devenv import DevenvError


def write_config(root, body: str):
    (root / devenv.CONFIG_NAME).write_text(body)


# --- resolution ---------------------------------------------------------------

def test_no_config_file_is_the_shipped_layout(tmp_path):
    """A fresh clone works before anyone writes any config."""
    dv, warnings = devenv.load(tmp_path, environ={})
    assert dv.root == tmp_path / "devenv"
    assert dv.reference == tmp_path / "devenv" / "reference"
    assert dv.workspace == tmp_path / "devenv" / "workspace"
    assert dv.config_path is None
    assert warnings == []


def test_explicit_config_is_honoured(tmp_path):
    write_config(tmp_path, "devenv:\n  root: env\n  reference: refs\n  workspace: work\n")
    dv, warnings = devenv.load(tmp_path, environ={})
    assert dv.reference == tmp_path / "env" / "refs"
    assert dv.workspace == tmp_path / "env" / "work"
    assert dv.config_path == tmp_path / devenv.CONFIG_NAME
    assert warnings == []


def test_partial_config_falls_back_per_key(tmp_path):
    write_config(tmp_path, "devenv:\n  reference: refs\n")
    dv, _ = devenv.load(tmp_path, environ={})
    assert dv.reference == tmp_path / "devenv" / "refs"
    assert dv.workspace == tmp_path / "devenv" / "workspace"


def test_unknown_key_warns_but_does_not_fail(tmp_path):
    write_config(tmp_path, "devenv:\n  root: devenv\n  corpora: reference\n")
    dv, warnings = devenv.load(tmp_path, environ={})
    assert dv.reference == tmp_path / "devenv" / "reference"
    assert any("corpora" in w for w in warnings)


def test_env_override_wins_over_the_configured_root(tmp_path):
    write_config(tmp_path, "devenv:\n  root: devenv\n")
    elsewhere = tmp_path / "elsewhere"
    dv, _ = devenv.load(tmp_path, environ={devenv.ROOT_ENV: str(elsewhere)})
    assert dv.root == elsewhere
    assert dv.reference == elsewhere / "reference"


# --- a room cannot escape the root -------------------------------------------

@pytest.mark.parametrize("room", ["../escape", "/abs/path", "..", "a/b", "Ref", ""])
def test_a_room_is_one_safe_segment(tmp_path, room):
    write_config(tmp_path, f"devenv:\n  reference: {room!r}\n")
    with pytest.raises(DevenvError) as exc:
        devenv.load(tmp_path, environ={})
    assert "devenv.reference" in str(exc.value)


def test_rooms_must_be_distinct(tmp_path):
    write_config(tmp_path, "devenv:\n  reference: same\n  workspace: same\n")
    with pytest.raises(DevenvError, match="distinct"):
        devenv.load(tmp_path, environ={})


def test_a_malformed_config_is_an_error_not_a_fallback(tmp_path):
    write_config(tmp_path, "devenv: [not, a, mapping]\n")
    with pytest.raises(DevenvError, match="must be a mapping"):
        devenv.load(tmp_path, environ={})


# --- the shape exists before anything writes ---------------------------------

def test_ensure_creates_both_rooms_and_is_idempotent(tmp_path):
    dv, _ = devenv.load(tmp_path, environ={})
    dv.ensure()
    assert dv.reference.is_dir() and dv.workspace.is_dir()
    dv.ensure()  # a second run must not raise
    assert dv.reference.is_dir()


# --- strays: nothing scans them, so they are named ---------------------------

def test_a_checkout_in_neither_room_is_reported(tmp_path, capsys):
    dv, _ = devenv.load(tmp_path, environ={})
    dv.ensure()
    (dv.root / "half-mounted").mkdir()
    assert dv.strays() == ["half-mounted"]

    devenv.print_devenv(dv, tmp_path)
    out = capsys.readouterr().out
    assert "stray" in out and "half-mounted" in out
    assert "reference/ or workspace/" in out


def test_a_tidy_devenv_reports_both_rooms_and_no_strays(tmp_path, capsys):
    source = tmp_path / "src"
    write_source(source, MARKDOWN_DOCS)
    git_commit_all(source)
    dv, _ = devenv.load(tmp_path, environ={})
    dv.ensure()
    mount(dv.reference, "demo-course", source, ALL_MODES, MARKDOWN_ADAPTER)

    devenv.print_devenv(dv, tmp_path)
    out = capsys.readouterr().out
    assert "devenv/reference" in out and "1 corpus" in out
    assert "devenv/workspace" in out and "(empty)" in out
    assert "stray" not in out


# --- the legacy tree stops the CLI rather than half-working ------------------

def test_legacy_corpora_names_the_move(tmp_path):
    (tmp_path / "corpora" / "demo-course").mkdir(parents=True)
    with pytest.raises(DevenvError) as exc:
        devenv.load(tmp_path, environ={})
    message = str(exc.value)
    assert "corpora/ still holds mounted corpora" in message
    assert "mv corpora/demo-course" in message
    assert str(tmp_path / "devenv" / "reference") in message


def test_legacy_corpora_is_ignored_once_reference_is_populated(tmp_path):
    """A leftover corpora/ after a completed move must not block anything."""
    (tmp_path / "corpora" / "leftover").mkdir(parents=True)
    (tmp_path / "devenv" / "reference" / "demo-course").mkdir(parents=True)
    dv, _ = devenv.load(tmp_path, environ={})
    assert dv.reference == tmp_path / "devenv" / "reference"


def test_an_empty_legacy_corpora_is_not_a_migration(tmp_path):
    (tmp_path / "corpora").mkdir()
    dv, _ = devenv.load(tmp_path, environ={})
    assert dv.count(dv.reference) == 0


# --- through the CLI ----------------------------------------------------------

def test_ch_devenv_reports_an_injected_reference_room(markdown_corpus, capsys):
    """An injected room bypasses config resolution; the report says what it was
    handed rather than claiming a chiron.yaml it never read."""
    from conftest import run
    reference = markdown_corpus[0]
    code, out = run(reference, "devenv", capsys=capsys)
    assert code == 0
    assert "reference" in out and "1 corpus" in out
    assert "workspace" in out
    assert f"(defaults — no {devenv.CONFIG_NAME})" in out
