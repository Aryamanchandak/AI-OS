#!/usr/bin/env bash
# Plan 01, Work Package B — repeatable root-level baseline command.
#
# Runs the currently-canonical lint/type/test/OpenAPI-staleness checks for
# each of GLC, ingestion, and the gateway, plus the shell's checks, and
# records pass/fail per step. Does NOT fix failures — recording a red
# baseline is the point (moving/fixing source is out of scope for Plan 01).
#
# Usage: bash migration/baseline/run-baselines.sh
# Output: migration/baseline/results-<UTC timestamp>.log

set -u
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$ROOT/migration/baseline/results-$STAMP.log"

run_step() {
  local label="$1"; shift
  echo "### $label" | tee -a "$LOG"
  echo "\$ $*" | tee -a "$LOG"
  if ( "$@" ) >>"$LOG" 2>&1; then
    echo "RESULT: PASS" | tee -a "$LOG"
  else
    echo "RESULT: FAIL (exit $?)" | tee -a "$LOG"
  fi
  echo "" | tee -a "$LOG"
}

echo "Baseline run started $STAMP UTC" | tee "$LOG"
echo "" | tee -a "$LOG"

# --- GLC ---
( cd "$ROOT/glc_v5" && run_step "glc: ruff check" uv run ruff check . )
( cd "$ROOT/glc_v5" && run_step "glc: ruff format --check" uv run ruff format --check . )
( cd "$ROOT/glc_v5" && run_step "glc: mypy (advisory)" uv run mypy glc tests )
( cd "$ROOT/glc_v5" && run_step "glc: pytest (CI subset, excludes live/model/channel/voice-slot tests)" \
    uv run pytest tests/ -m "not requires_live_api and not requires_models" \
      --ignore=tests/channels --ignore=tests/voice/stt --ignore=tests/voice/tts )
( cd "$ROOT/glc_v5" && run_step "glc: validate_envelope" uv run python scripts/validate_envelope.py )
( cd "$ROOT/glc_v5" && run_step "glc: validate_policy" uv run python scripts/validate_policy.py )

# --- Ingestion (merged-ingestion is the protected active app; read-only checks only) ---
( cd "$ROOT/ingestion-pipeline/merged-ingestion" && run_step "ingestion: pytest" bash scripts/run.sh pytest -q )
( cd "$ROOT/ingestion-pipeline/merged-ingestion" && run_step "ingestion: verify_environment" bash scripts/run.sh python scripts/verify_environment.py )
( cd "$ROOT/ingestion-pipeline/merged-ingestion" && run_step "ingestion: mypy --strict cockpit/server.py" ./.venv/bin/python -m mypy --strict cockpit/server.py )

# --- Gateway (uses ingestion's venv per gateway/README.md) ---
GW_PY="$ROOT/ingestion-pipeline/merged-ingestion/.venv/bin/python"
( cd "$ROOT/gateway" && run_step "gateway: pytest (checks openapi.json staleness)" "$GW_PY" -m pytest )
( cd "$ROOT/gateway" && run_step "gateway: export_openapi (staleness check)" "$GW_PY" export_openapi.py )
( cd "$ROOT/gateway" && run_step "gateway: mypy --strict main.py" "$GW_PY" -m mypy --config-file mypy.ini main.py )

# --- Shell ---
( cd "$ROOT/shell" && run_step "shell: types:generate" npm run types:generate )
( cd "$ROOT/shell" && run_step "shell: tsc -b" npx tsc -b )
( cd "$ROOT/shell" && run_step "shell: vite build" npx vite build )
( cd "$ROOT/shell" && run_step "shell: vitest run" npx vitest run )

echo "Baseline run finished. Log: $LOG"
