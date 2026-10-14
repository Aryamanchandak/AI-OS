#!/bin/zsh
# Run only the vector consumer (pending items -> chunks -> ChromaDB via Ollama).
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
exec "$REPO/.venv/bin/python" -m pipeline.vector.run "$@"
