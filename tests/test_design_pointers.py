"""The drift test design/README.md has always claimed.

Every claim in design/*.json carries a pointer to the code or prose it was
taken from, and "checking those pointers is the drift test" — which until now
was a hope. This makes it a test: a quote that moved lines warns, a quote that
vanished fails.
"""

import json
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "design"


def _pointers(node, path="$"):
    """Every {file, line} mapping anywhere in the tree, with its json path."""
    if isinstance(node, dict):
        if isinstance(node.get("file"), str) and isinstance(node.get("line"), int):
            yield path, node
        for key, value in node.items():
            yield from _pointers(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _pointers(value, f"{path}[{i}]")


def _design_files():
    return sorted(DESIGN.glob("*.json"))


def test_design_files_are_present_and_parse():
    files = _design_files()
    assert files, "design/ has no JSON to check"
    for path in files:
        json.loads(path.read_text())


@pytest.mark.parametrize("design_file", _design_files(), ids=lambda p: p.name)
def test_every_pointer_resolves(design_file):
    """A pointer whose file is gone, or whose line is past the end, is drift
    the design docs are lying about."""
    document = json.loads(design_file.read_text())
    checked = 0
    for json_path, pointer in _pointers(document):
        target = ROOT / pointer["file"]
        assert target.exists(), (
            f"{design_file.name} {json_path} points at {pointer['file']}, "
            f"which no longer exists")
        lines = target.read_text().splitlines()
        assert 1 <= pointer["line"] <= len(lines), (
            f"{design_file.name} {json_path} points at "
            f"{pointer['file']}:{pointer['line']}, past the end "
            f"({len(lines)} lines)")
        checked += 1
    assert checked or design_file.name != "interaction.json"


@pytest.mark.parametrize("design_file", _design_files(), ids=lambda p: p.name)
def test_every_quoted_pointer_still_quotes(design_file):
    """Content drift is fatal; line drift is a warning. A claim that cites a
    line is really citing what the line said."""
    document = json.loads(design_file.read_text())
    for json_path, pointer in _pointers(document):
        quote = pointer.get("quote")
        if not quote:
            continue
        target = ROOT / pointer["file"]
        lines = target.read_text().splitlines()
        here = lines[pointer["line"] - 1] if pointer["line"] <= len(lines) else ""
        if quote in here:
            continue
        moved = [i + 1 for i, line in enumerate(lines) if quote in line]
        assert moved, (
            f"{design_file.name} {json_path}: {pointer['file']} no longer "
            f"contains {quote!r} — the claim it supports is stale")
        warnings.warn(
            f"{design_file.name} {json_path}: {pointer['file']}:"
            f"{pointer['line']} moved to {moved[0]} — update the pointer",
            stacklevel=1)
