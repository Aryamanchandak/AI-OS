"""Compatibility entry point for ``uvicorn main:app``.

Application code lives in the installable ``gateway`` package under ``src``.
"""

from __future__ import annotations

from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parent / "src"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from gateway.app.main import (  # noqa: E402,F401
    AI_OS_ROOT,
    SCHEMA_AND_DOCS_PATHS,
    SHELL_DIST,
    app,
    create_app,
)


if __name__ == "__main__":
    import uvicorn
    from gateway.platform.service_registry import gateway_address

    address = gateway_address()
    uvicorn.run("main:app", host=address.host, port=address.port, reload=False)
