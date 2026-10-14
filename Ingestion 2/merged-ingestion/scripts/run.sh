#!/usr/bin/env bash
set -euo pipefail

# The environment is prepared non-editably by bootstrap_environment.sh.
# --no-sync prevents a normal `uv run` from recreating the broken hidden .pth.
exec uv run --no-sync "$@"
