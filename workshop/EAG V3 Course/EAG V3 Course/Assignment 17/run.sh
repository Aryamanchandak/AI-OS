#!/bin/sh
# Starts the three services: glc_v5 (models, keys), S17Code (the coding engine), and this app.
# Ctrl-C stops all three.
set -eu
cd "$(dirname "$0")"
HERE=$(pwd)

[ -d S17Code ] && [ -d glc_v5 ] || { echo "Clone S17Code and glc_v5 into this folder first (see README)."; exit 1; }
command -v node >/dev/null || { echo "node is required: the check that judges each tool runs on it."; exit 1; }

# One control token, shared by the engine and this app. Generated once, kept in .env, never printed.
[ -f .env ] || cp .env.example .env
if ! grep -q '^S17_CONTROL_TOKEN=..*' .env; then
  TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  grep -v '^S17_CONTROL_TOKEN=' .env > .env.tmp && echo "S17_CONTROL_TOKEN=$TOKEN" >> .env.tmp && mv .env.tmp .env
fi
S17_CONTROL_TOKEN=$(grep '^S17_CONTROL_TOKEN=' .env | cut -d= -f2-)
export S17_CONTROL_TOKEN

mkdir -p workspace
trap 'kill 0' INT TERM EXIT

(cd glc_v5 && uv run python -m glc.cli serve) &

# The engine may edit only ./workspace, may run only node, and may not touch the judge.
(cd S17Code && \
  S17_WORKSPACE="$HERE/workspace" \
  S17_ALLOWED_COMMANDS=node \
  S17_PROTECTED_PATHS='checks/**,SPEC.md' \
  S17_SKILLS_DIR="$HERE/skills" \
  S17_MAX_REPEAT_FAILURES=4 \
  uv run python -m s17code.cli serve) &

python3 -m ftb &
wait
