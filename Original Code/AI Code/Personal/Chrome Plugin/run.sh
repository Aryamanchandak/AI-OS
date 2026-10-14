#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
  echo "Creating .venv..."
  python3 -m venv .venv
fi

if [ ! -x ".venv/bin/python" ] || ! .venv/bin/python -c "import sys" >/dev/null 2>&1; then
  echo "Existing .venv is broken. Rebuild it with:"
  echo "  rm -rf .venv"
  echo "  ./run.sh"
  exit 1
fi

.venv/bin/python -m pip install -q -r requirements.txt
exec .venv/bin/python server.py
