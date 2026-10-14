#!/bin/zsh
# One-command Obsidian ingestion. Run from anywhere:
#
#   ~/Documents/AI\ Code/ingestion-pipeline/scripts/ingest_obsidian.sh            # full run
#   ~/Documents/AI\ Code/ingestion-pipeline/scripts/ingest_obsidian.sh --dry-run  # preview only
#
# What it does:
#   1. Reads your Obsidian vault (filtered by config/obsidian_filters.txt)
#   2. Captures every new/changed note to immutable bronze + the ledger
#   3. Runs the KG consumer (Claude triplets -> Neo4j) — skipped on --dry-run
#   4. Runs the vector consumer (chunks -> ChromaDB via Ollama) — skipped on --dry-run
# Steps 3 and 4 tolerate Neo4j/Ollama being down: captured notes stay "pending"
# in the ledger and are picked up automatically on the next run.

set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "First run: creating venv and installing the pipeline..."
  PYBIN="$(command -v python3.11 || command -v /opt/homebrew/bin/python3.11 || command -v python3)"
  "$PYBIN" -m venv "$REPO/.venv" || exit 1
  "$REPO/.venv/bin/pip" install --quiet -e "$REPO" || exit 1
fi

echo "== Obsidian -> bronze =="
"$PY" -m pipeline.core.obsidian "$@" || exit 1

for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && exit 0
done

# Secrets (API keys) live in config/secrets.env — gitignored, one place to edit.
[[ -f "$REPO/config/secrets.env" ]] && source "$REPO/config/secrets.env"

echo "\n== KG consumer (Neo4j) =="
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "SKIPPED: ANTHROPIC_API_KEY is not set. Put it in $REPO/config/secrets.env"
  echo "         (one line:  export ANTHROPIC_API_KEY=sk-ant-...). Items stay pending."
else
  "$PY" -m pipeline.kg.run || echo "KG run failed — items stay pending; re-run later."
fi

echo "\n== Vector consumer (ChromaDB) =="
"$PY" -m pipeline.vector.run || echo "Vector run failed — items stay pending; re-run later."

echo "\nDone."
