"""Entry point: `python main.py` or `uvicorn main:app`. The code is the `gateway` package under `src/`."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from gateway.app import SCHEMA_AND_DOCS_PATHS, app, create_app  # noqa: E402,F401
from gateway.config import AI_OS_ROOT  # noqa: E402,F401


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
