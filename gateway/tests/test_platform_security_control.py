from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from gateway.app.main import create_app
from gateway.audit import AuditStore
from gateway.platform.configuration import GLCPaths
from gateway.platform.startup import StartupCheck, StartupDependencyError
from gateway.ledger import CallLedger


@pytest.fixture
def glc_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path | str]:
    values: dict[str, Path | str] = {
        "audit": tmp_path / "audit.sqlite",
        "ledger": tmp_path / "gateway.sqlite",
    }
    monkeypatch.setenv("GLC_AUDIT_DB", str(values["audit"]))
    monkeypatch.setenv("GLC_GATEWAY_DB", str(values["ledger"]))
    return values


def test_database_defaults_are_centralized_under_database_sqlite() -> None:
    paths = GLCPaths(environment={})
    for path in (paths.ledger_db, paths.audit_db):
        assert path.parent.name == "sqlite"
        assert path.parent.parent.name == "Database"
        assert ".glc" not in str(path)


def test_caller_supplied_startup_check_refuses_startup_and_names_it(
    glc_environment: dict[str, Path | str],
) -> None:
    """Injected startup failures name the dependency that failed."""

    def broken() -> None:
        raise ConnectionError("unreachable")

    app = create_app(
        token="gateway-token",
        startup_checks=(StartupCheck("injected dependency", broken),),
    )
    with pytest.raises(StartupDependencyError, match="injected dependency"):
        with TestClient(app):
            pass


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


def test_startup_creates_only_audit_and_ledger_databases(glc_environment, tmp_path) -> None:
    with TestClient(create_app(token='gateway-token')):
        assert {path.name for path in tmp_path.glob('*.sqlite')} == {'audit.sqlite', 'gateway.sqlite'}
