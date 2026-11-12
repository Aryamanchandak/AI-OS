#!/usr/bin/env bash
# Vector consumer entry point — what the Automator "ingest" button runs.
#
# Passes PYTHONPATH explicitly because the editable .pth install is unreliable
# in these uv venvs (knowledge_graph has the same quirk). RAW_DATA_ROOT points
# at the shared bronze/ledger core; CHROMA_PATH is optional.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RAW_DATA_ROOT="${RAW_DATA_ROOT:-$(cd "$HERE/../Raw Data" && pwd)}"
export PYTHONPATH="$HERE/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$HERE/.venv/bin/python" -m vector_db.run "$@"
