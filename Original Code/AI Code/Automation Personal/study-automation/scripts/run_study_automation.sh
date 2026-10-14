#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
STUDY_SYSTEM_ROOT="$(cd -- "${REPO_ROOT}/../../Learning System" >/dev/null 2>&1 && pwd)"

# Runtime logs must never live inside a repository (plan 02 §12 done
# criterion: "No runtime data is written inside the repository"). Resolve the
# same central Database root that study-system's config/baseline.json
# resolves to, unless explicitly overridden.
if [[ -n "${STUDY_SYSTEM_LOG_ROOT:-}" ]]; then
  LOG_DIR="${STUDY_SYSTEM_LOG_ROOT}"
elif [[ -n "${STUDY_SYSTEM_DATABASE_ROOT:-}" ]]; then
  LOG_DIR="${STUDY_SYSTEM_DATABASE_ROOT}/Logs/study_system"
else
  ANCESTOR="${REPO_ROOT}"
  DATABASE_ROOT=""
  while [[ "${ANCESTOR}" != "/" ]]; do
    if [[ "$(basename -- "${ANCESTOR}")" == "AI Code" ]]; then
      DATABASE_ROOT="${ANCESTOR}/Database"
      break
    fi
    ANCESTOR="$(dirname -- "${ANCESTOR}")"
  done
  if [[ -z "${DATABASE_ROOT}" ]]; then
    echo "Could not resolve a central Database root (no 'AI Code' ancestor found)." >&2
    echo "Set STUDY_SYSTEM_LOG_ROOT or STUDY_SYSTEM_DATABASE_ROOT explicitly." >&2
    exit 1
  fi
  LOG_DIR="${DATABASE_ROOT}/Logs/study_system"
fi
LOG_FILE="${LOG_DIR}/study_automation_$(date -u +%Y%m%dT%H%M%SZ).log"

cd "${REPO_ROOT}"

# study_system's own dependencies (pydantic, anthropic, openai, ...) live in
# the sibling study-system project's virtualenv. This project has no
# dependencies of its own beyond what study_system already declares, so it
# reuses that environment rather than duplicating a dependency set.
if [[ -d "${STUDY_SYSTEM_ROOT}/.venv" ]]; then
  # shellcheck disable=SC1091
  source "${STUDY_SYSTEM_ROOT}/.venv/bin/activate"
fi

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    if "${candidate}" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1; then
      PYTHON_BIN="${candidate}"
      break
    fi
  fi
done

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "Python 3.11 or newer is required." >&2
  exit 1
fi

"${PYTHON_BIN}" -c "import pydantic" >/dev/null 2>&1 || {
  echo "Missing Python dependencies. Activate study-system's project environment first." >&2
  echo "Expected setup example: (cd \"${STUDY_SYSTEM_ROOT}\" && uv sync --no-dev)" >&2
  exit 1
}

"${PYTHON_BIN}" -c "import sys; sys.path.insert(0, '${STUDY_SYSTEM_ROOT}/src'); import study_system" >/dev/null
mkdir -p "${LOG_DIR}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

log "study automation preflight started" | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" "${REPO_ROOT}/generate.py" --check "$@" 2>&1 | tee -a "${LOG_FILE}"
log "study automation generation started" | tee -a "${LOG_FILE}"
"${PYTHON_BIN}" "${REPO_ROOT}/generate.py" "$@" 2>&1 | tee -a "${LOG_FILE}"
log "study automation completed" | tee -a "${LOG_FILE}"
