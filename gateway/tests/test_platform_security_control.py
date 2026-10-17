from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from gateway.app.main import create_app
from gateway.audit import AuditStore
from gateway.platform.configuration import GLCPaths
from gateway.platform.startup import StartupCheck, StartupDependencyError
from gateway.security.ssrf import prepare_safe_target
from gateway.ledger import CallLedger


@pytest.fixture
def glc_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path | str]:
    values: dict[str, Path | str] = {
        "audit": tmp_path / "audit.sqlite",
        "ledger": tmp_path / "gateway.sqlite",
        "cache": tmp_path / "semantic_cache.sqlite",
    }
    monkeypatch.setenv("GLC_AUDIT_DB", str(values["audit"]))
    monkeypatch.setenv("GLC_GATEWAY_DB", str(values["ledger"]))
    monkeypatch.setenv("GLC_CACHE_DB", str(values["cache"]))
    return values


def test_database_defaults_are_centralized_under_database_sqlite() -> None:
    paths = GLCPaths(environment={})
    for path in (paths.ledger_db, paths.audit_db, paths.cache_db):
        assert path.parent.name == "sqlite"
        assert path.parent.parent.name == "Database"
        assert ".glc" not in str(path)


def test_caller_supplied_startup_check_refuses_startup_and_names_it(
    glc_environment: dict[str, Path | str],
) -> None:
    """`build_container`'s `startup_checks` extension point re-raises a
    caller-injected failure with a structured, named error. This is a
    harness test, not dependency-specific: it proves the plumbing, not any
    particular dependency's real check.

    Plan 03's decision #2 table also lists a semantic-cache row as
    fail-hard, but no cache backend is imported under this plan — the
    Goal section's confirmed `git filter-repo` path list (`glc/config.py`,
    `glc/db.py`, `glc/audit/`, `glc/security/`, `glc/policy/`,
    `glc/routes/control.py`) excludes `glc/cache/` and `glc/economics/`
    entirely. That table row is therefore unimplementable until whichever
    later plan imports the cache (Plan 04, since semantic cache sits on
    the chat request path) does so and wires a real health check for it.
    Real telemetry coverage lives in
    `test_configured_unreachable_telemetry_target_fails_real_startup`
    below, against the actual `Telemetry` object, not an injected fake.
    """

    def broken() -> None:
        raise ConnectionError("unreachable")

    app = create_app(
        token="gateway-token",
        startup_checks=(StartupCheck("injected dependency", broken),),
    )
    with pytest.raises(StartupDependencyError, match="injected dependency"):
        with TestClient(app):
            pass


def test_broken_semantic_cache_backend_refuses_real_startup(
    glc_environment: dict[str, Path | str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    invalid_database = tmp_path / "cache-is-a-directory"
    invalid_database.mkdir()
    monkeypatch.setenv("GLC_CACHE_DB", str(invalid_database))
    with pytest.raises(StartupDependencyError) as caught:
        with TestClient(create_app(token="gateway-token")):
            pass
    event = json.loads(str(caught.value))
    assert event["dependency"] == "semantic cache"
    assert event["event"] == "gateway.startup.dependency_failed"


def test_configured_unreachable_telemetry_target_fails_real_startup(
    glc_environment: dict[str, Path | str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    with pytest.raises(StartupDependencyError, match="telemetry export"):
        with TestClient(create_app(token="gateway-token")):
            pass


def test_audit_is_append_only_and_fail_closed(tmp_path: Path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite")
    assert not hasattr(store, "update") and not hasattr(store, "delete")
    store.database.path = tmp_path  # a directory cannot be opened as SQLite
    with pytest.raises(Exception):
        store.append(
            channel="control",
            channel_user_id="owner",
            trust_level="owner_paired",
            event_type="must-not-disappear",
        )


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd"],
)
def test_ssrf_guard_rejects_internal_and_non_http_targets(url: str) -> None:
    with pytest.raises(HTTPException) as caught:
        prepare_safe_target(url)
    assert caught.value.status_code == 400


def test_call_ledger_keeps_its_own_schema_and_database(tmp_path: Path) -> None:
    ledger = CallLedger(tmp_path / "gateway.sqlite")
    row_id = ledger.append(provider="test", model="model", agent="agent-1", usd=0.25)
    assert row_id > 0
    assert ledger.recent(1)[0]["agent"] == "agent-1"
    assert not (tmp_path / "audit.sqlite").exists()


def test_gateway_code_has_no_legacy_glc_imports() -> None:
    source = Path(__file__).resolve().parents[1] / "src" / "gateway"
    offenders = [
        path.relative_to(source).as_posix()
        for path in source.rglob("*.py")
        if "from glc" in path.read_text(encoding="utf-8")
        or "import glc" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
