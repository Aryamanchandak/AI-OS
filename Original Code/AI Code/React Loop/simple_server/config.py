"""Runtime configuration shared by MCP tools."""

from __future__ import annotations

import os

_DEFAULT_APP_BASE_URL = "http://127.0.0.1:8000"


def app_base_url() -> str:
    """Return the configured web-app base URL without a trailing slash."""
    return os.getenv("APP_BASE_URL", _DEFAULT_APP_BASE_URL).rstrip("/")


def app_url(path: str) -> str:
    """Build an absolute URL for a web-app route."""
    route = path if path.startswith("/") else f"/{path}"
    return f"{app_base_url()}{route}"
