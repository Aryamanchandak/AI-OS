# `src/consequence_radar/__main__.py` — explained

This tiny file exists so the package can be launched with `python -m consequence_radar`, which is exactly what the `radar` shell script does for its `start`/`run` subcommands (`exec uv run ... python -m consequence_radar "$@"`).

It has one job: import `run` from `.web.app` (L3) and call it under the standard `if __name__ == "__main__":` guard (L6). All actual startup logic — building the FastAPI/Flask-style app (whichever framework `web/app.py` uses), wiring routes, starting the server — lives in `web/app.py:run()`; this file is purely a launcher shim with no logic of its own.

Because the import is a relative import (`from .web.app import run`), this file only works when `consequence_radar` is imported as a package (which is guaranteed when invoked via `-m`), not when `web/app.py` is run directly as a standalone script.
