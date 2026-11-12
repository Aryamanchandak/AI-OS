#!/bin/zsh
# Run only the KG consumer (pending items -> Claude triplets -> Neo4j).
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
exec "$REPO/.venv/bin/python" -m pipeline.kg.run "$@"
