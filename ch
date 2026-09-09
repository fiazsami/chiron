#!/bin/sh
# chiron's CLI, scoped. `./ch status` == `uv run python -m tools.lingua status`.
# Run from the repo root (the same constraint the module form already has).
# Symlink it onto PATH if you prefer bare `ch`.
exec uv run python -m tools.lingua "$@"
