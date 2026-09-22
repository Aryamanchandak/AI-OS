from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from gateway.app.main import create_app
from gateway.platform.configuration import load_gateway_settings
from gateway.platform.service_registry import load_service_registry


def _write_registry(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_duplicate_enabled_ports_fail_loudly(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path / "services.yaml",
        """services:
  alpha: {host: 127.0.0.1, port: 8120, enabled: true}
  beta: {host: 127.0.0.1, port: 8120, enabled: true}
""",
    )
    with pytest.raises(ValueError, match="duplicate enabled service port 8120"):
        load_service_registry(registry, environment={})


def test_port_overrides_receive_the_same_duplicate_validation(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path / "services.yaml",
        """services:
  alpha: {host: 127.0.0.1, port: 8120, enabled: true}
  beta: {host: 127.0.0.1, port: 8121, enabled: true}
""",
    )
    with pytest.raises(ValueError, match="duplicate enabled service port 8120"):
        load_service_registry(registry, environment={"AI_OS_SERVICE_BETA_PORT": "8120"})


def test_missing_and_malformed_configuration_fail_during_construction(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(ValueError, match="does not exist"):
        load_gateway_settings(missing)
    malformed = tmp_path / "gateway.yaml"
    malformed.write_text("host: [broken", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        load_gateway_settings(malformed)


def test_missing_registry_prevents_application_startup(tmp_path: Path) -> None:
    app = create_app(service_registry_path=tmp_path / "missing-services.yaml")
    with pytest.raises(ValueError, match="Service registry does not exist"):
        with TestClient(app):
            pass


def test_malformed_registry_prevents_application_startup(tmp_path: Path) -> None:
    malformed = tmp_path / "services.yaml"
    malformed.write_text("services: [broken", encoding="utf-8")
    app = create_app(service_registry_path=malformed)
    with pytest.raises(ValueError, match="Service registry is malformed"):
        with TestClient(app):
            pass


@pytest.mark.parametrize(
    ("override", "message"),
    (
        ({"AI_OS_SERVICE_ALPHA_HOST": "https://not-a-host"}, "host must be"),
        ({"AI_OS_SERVICE_ALPHA_PORT": "0"}, "greater than or equal to 1"),
        ({"AI_OS_SERVICE_ALPHA_PORT": "not-a-port"}, "valid integer"),
    ),
)
def test_service_overrides_are_validated(
    tmp_path: Path, override: dict[str, str], message: str
) -> None:
    registry = _write_registry(
        tmp_path / "services.yaml",
        """services:
  alpha: {host: 127.0.0.1, port: 8120, enabled: true}
""",
    )
    with pytest.raises(ValueError, match=message):
        load_service_registry(registry, environment=override)


def test_authenticated_diagnostics_are_allow_listed_and_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_OS_TOKEN", "never-show-this-token")
    monkeypatch.setenv("DATABASE_PASSWORD", "never-show-this-password")
    monkeypatch.setenv("PROVIDER_API_KEY", "never-show-this-api-key")
    with TestClient(create_app(token="test-token")) as client:
        unauthorized = client.get("/api/diagnostics/services")
        assert unauthorized.status_code == 401
        response = client.get(
            "/api/diagnostics/services",
            headers={"Authorization": "Bearer test-token"},
        )
    assert response.status_code == 200
    serialized = json.dumps(response.json()).lower()
    assert "http://127.0.0.1:8000" in serialized
    assert "http://127.0.0.1:8111" in serialized
    assert "never-show" not in serialized
    assert "token" not in serialized
    assert "password" not in serialized
    assert "api_key" not in serialized


def test_sibling_path_injection_is_confined_to_the_temporary_adapter() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src"
    offenders = [
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*.py")
        if "sys.path" in path.read_text(encoding="utf-8")
    ]
    assert offenders == ["gateway/app/temporary_ingestion_adapter.py"]
