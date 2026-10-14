#!/bin/zsh
# running.sh — cascading launcher for local services this workspace depends on.
#
# Add a new service by appending another `start_<name>` function and a call
# to it at the bottom. Each function should be idempotent (safe to re-run,
# no-op if already up) and print one line of status.
#
# Usage: ./running.sh [--status]
#   --status   only report what's up/down, don't start anything

set -uo pipefail

STATUS_ONLY=0
[[ "${1:-}" == "--status" ]] && STATUS_ONLY=1

ok()   { print -P "%F{green}✓%f $1" }
warn() { print -P "%F{yellow}○%f $1" }
fail() { print -P "%F{red}✗%f $1" }

port_open() { nc -z -w2 localhost "$1" 2>/dev/null }

# --- Ollama (embeddings for the vector consumer) -----------------------
start_ollama() {
  if curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    ok "Ollama already running on :11434"
    return
  fi
  (( STATUS_ONLY )) && { fail "Ollama not running"; return }
  open -a Ollama
  for i in {1..10}; do
    curl -s -m 1 http://localhost:11434/api/tags >/dev/null 2>&1 && { ok "Ollama started"; return }
    sleep 1
  done
  fail "Ollama did not come up after 10s"
}

# --- Neo4j (knowledge graph store) --------------------------------------
start_neo4j() {
  if port_open 7687; then
    ok "Neo4j already running on :7687"
    return
  fi
  (( STATUS_ONLY )) && { fail "Neo4j not running"; return }
  warn "Neo4j not installed/configured yet — start it manually (Neo4j Desktop / docker / brew), then re-run"
}

# --- add more services below, e.g.:
# start_redis() { ... }
# start_postgres() { ... }

echo "== running.sh =="
start_ollama
start_neo4j
