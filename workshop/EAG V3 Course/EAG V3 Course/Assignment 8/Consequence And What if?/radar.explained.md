# `radar` — explained

`radar` is the project's single command-line entry point for local development. It is a POSIX `sh` script (not Python) that normalizes the working directory, makes sure dependencies are installed, and then hands off to `uv run` to execute the actual Python application or test suite. Nothing in the rest of the codebase is reachable without going through this script (or reproducing what it does by hand) unless the developer manually manages their own virtualenv and `PYTHONPATH`.

## What it does, step by step

1. **Pin the working directory (L7-8).** `PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)` resolves the script's own directory regardless of where it was invoked from, then `cd`s there. The comment at the top explains why: relative paths (like the SQLite file location or `.env`) need to resolve consistently no matter which directory the user happened to run `./radar` from.

2. **Check for `uv` (L10-13).** If the `uv` command isn't on `PATH`, it prints an install link and exits with status 1. The rest of the script assumes `uv` exists — there is no fallback to plain `pip`/`venv`.

3. **Bootstrap `.env` (L15-18).** If no `.env` file exists in the project root, it copies `.env.example` to `.env` and prints a reminder to add `GEMINI_API_KEY`. This means a fresh checkout "just works" for `./radar test` (offline tests don't need the key) but will silently produce an unconfigured `.env` — if the user forgets to fill in the key afterward, live runs will fail with whatever error the Gemini client raises, not a friendly message from this script.

4. **Set `PYTHONPATH` (L20-22).** `PYTHONPATH="$PROJECT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"` is exported so `consequence_radar` is importable without an editable pip install. The comment explains the reason: editable installs are unreliable when the parent directory path contains a literal `?` character — which is true of this very project directory (`.../Consequence And What if?`). This is a workaround for a specific, self-referential environment quirk, not a general best practice.

5. **Dispatch on subcommand (L24-46).** `command_name=${1:-start}` defaults to `start` if no argument is given, then the remaining args are shifted off and forwarded. The `case` statement supports:
   - `start` / `run` → `exec uv run --frozen --no-editable python -m consequence_radar "$@"` — launches the web app (see `src/consequence_radar/__main__.py`, which calls `web.app.run()`).
   - `test` → `exec uv run --frozen --no-editable --extra dev pytest "$@"` — runs the offline pytest suite with the `dev` extras installed.
   - `setup` → `exec uv sync --frozen --no-editable --extra dev "$@"` — installs locked dependencies only, without running anything.
   - `help` / `-h` / `--help` → prints usage and exits 0.
   - any other value → prints "Unknown command" to stderr and exits 2.

All three real subcommands use `exec`, so the shell process is replaced rather than spawning a child — signals and exit codes pass straight through to `uv`.

## Non-obvious details worth knowing

- `--frozen --no-editable` is used consistently, meaning the script will never silently update `uv.lock` or fall back to a mutable/editable install — dependency resolution is expected to already be locked and correct.
- The script has no argument validation beyond the subcommand name; anything after the subcommand is passed straight through to `uv run`/`pytest`/`uv sync` verbatim (`"$@"`), so e.g. `./radar test -k foo` works as expected.
- There's no `set -o pipefail`-equivalent concern here since there are no pipes; `set -eu` (L5) is enough to abort on the first failing command or unset variable.
- This script is the only documented way `__main__.py` and the web app get run in development; anyone bypassing it needs to replicate the `PYTHONPATH` export and `.env` presence manually.
