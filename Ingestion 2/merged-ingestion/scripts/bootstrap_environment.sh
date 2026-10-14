#!/usr/bin/env bash
set -euo pipefail

# On this macOS volume uv's editable `.pth` files are marked hidden and CPython
# skips them. Install local packages as normal wheels and verify the imports
# immediately. Use `scripts/run.sh` afterwards so uv does not silently switch
# the project back to editable mode.
uv sync --all-extras --no-editable "$@"
uv run --no-sync python scripts/verify_environment.py
