"""A2 — /docs, /redoc, /openapi.json must be off when GLC_ENV=production.

`glc.main` reads GLC_ENV at *import* time (`_PRODUCTION` is a module-level
constant), so this test reloads the module with the env var set rather than
just calling a function — that's the same shape the real deployed gateway
uses (modal_app.py's gateway image sets GLC_ENV=production via `.env()`
before the module is ever imported).
"""

from __future__ import annotations

import importlib
import sys

from fastapi.testclient import TestClient


def _reload_main_with_env(monkeypatch, env_value: str | None):
    if env_value is None:
        monkeypatch.delenv("GLC_ENV", raising=False)
    else:
        monkeypatch.setenv("GLC_ENV", env_value)
    sys.modules.pop("glc.main", None)
    return importlib.import_module("glc.main")


def test_docs_and_openapi_disabled_when_production(monkeypatch):
    m = _reload_main_with_env(monkeypatch, "production")
    try:
        with TestClient(m.app) as c:
            assert c.get("/docs").status_code == 404
            assert c.get("/redoc").status_code == 404
            assert c.get("/openapi.json").status_code == 404
    finally:
        sys.modules.pop("glc.main", None)


def test_docs_and_openapi_enabled_by_default_for_local_dev(monkeypatch):
    m = _reload_main_with_env(monkeypatch, None)
    try:
        with TestClient(m.app) as c:
            assert c.get("/docs").status_code == 200
            assert c.get("/openapi.json").status_code == 200
    finally:
        sys.modules.pop("glc.main", None)
