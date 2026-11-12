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
from gateway.policy import PolicyEngine
from gateway.security import PairingStore, RateLimiter
from gateway.security.ssrf import prepare_safe_target
from gateway.ledger import CallLedger


@pytest.fixture
def glc_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path | str]:
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "rules:\n  - {tool: ping, action: allow, reason: version-one}\n",
        encoding="utf-8",
    )
    channels = tmp_path / "channels.yaml"
    channels.write_text(
        "defaults:\n  rate_limits: {messages_per_minute: 2, tool_calls_per_minute: 1}\n"
        "channels: {}\n",
        encoding="utf-8",
    )
    values: dict[str, Path | str] = {
        "policy": policy,
        "channels": channels,
        "audit": tmp_path / "audit.sqlite",
        "pairing": tmp_path / "pairings.sqlite",
        "ledger": tmp_path / "gateway.sqlite",
        "cache": tmp_path / "semantic_cache.sqlite",
        "token_file": tmp_path / "install_token",
        "token": "install-token-for-tests",
    }
    Path(values["token_file"]).write_text(str(values["token"]), encoding="utf-8")
    monkeypatch.setenv("GLC_POLICY_YAML", str(values["policy"]))
    monkeypatch.setenv("GLC_CHANNELS_YAML", str(values["channels"]))
    monkeypatch.setenv("GLC_AUDIT_DB", str(values["audit"]))
    monkeypatch.setenv("GLC_PAIRING_DB", str(values["pairing"]))
    monkeypatch.setenv("GLC_GATEWAY_DB", str(values["ledger"]))
    monkeypatch.setenv("GLC_CACHE_DB", str(values["cache"]))
    monkeypatch.setenv("GLC_INSTALL_TOKEN_FILE", str(values["token_file"]))
    return values


def test_database_defaults_are_centralized_under_database_sqlite() -> None:
    paths = GLCPaths(environment={})
    for path in (paths.ledger_db, paths.audit_db, paths.pairing_db, paths.cache_db):
        assert path.parent.name == "sqlite"
        assert path.parent.parent.name == "Database"
        assert ".glc" not in str(path)


def test_malformed_policy_refuses_startup_with_structured_dependency(
    glc_environment: dict[str, Path | str],
) -> None:
    Path(glc_environment["policy"]).write_text("rules: [broken", encoding="utf-8")
    with pytest.raises(StartupDependencyError) as caught:
        with TestClient(create_app(token="gateway-token")):
            pass
    event = json.loads(str(caught.value))
    assert event["dependency"] == "policy.yaml"
    assert event["event"] == "gateway.startup.dependency_failed"


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


def test_policy_reload_route_preserves_auth_and_audits(
    glc_environment: dict[str, Path | str],
) -> None:
    headers = {"Authorization": f"Bearer {glc_environment['token']}"}
    with TestClient(create_app(token="gateway-token")) as client:
        assert client.post("/v1/control/reload-policy").status_code == 401
        assert client.post(
            "/v1/control/reload-policy", headers={"Authorization": "Bearer wrong"}
        ).status_code == 403
        Path(glc_environment["policy"]).write_text(
            "rules:\n  - {tool: ping, action: deny, reason: version-two}\n",
            encoding="utf-8",
        )
        response = client.post("/v1/control/reload-policy", headers=headers)
        assert response.status_code == 200
    rows = AuditStore(Path(glc_environment["audit"])).query()
    assert rows[0]["event_type"] == "policy_reloaded"
    assert '"trigger": "http"' in rows[0]["params_json"]


def test_pairing_and_presence_contract_round_trip(
    glc_environment: dict[str, Path | str],
) -> None:
    headers = {"Authorization": f"Bearer {glc_environment['token']}"}
    with TestClient(create_app(token="gateway-token")) as client:
        issued = client.post(
            "/v1/control/pair",
            headers=headers,
            json={"channel": "telegram", "channel_user_id": "42"},
        )
        assert issued.status_code == 200
        confirmed = client.post(
            "/v1/control/pair/confirm",
            headers=headers,
            json={"code": issued.json()["code"]},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["trust_level"] == "user_paired"
        presence = client.get("/v1/control/presence", headers=headers)
        assert presence.status_code == 200
        assert presence.json()["paired_users"][0]["channel"] == "telegram"


def test_kill_compatibility_suspends_only_glc(
    glc_environment: dict[str, Path | str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLC_KILL_ALLOW_REMOTE", "1")
    headers = {"Authorization": f"Bearer {glc_environment['token']}"}
    with TestClient(create_app(token="gateway-token")) as client:
        response = client.post("/v1/control/kill", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "terminating"
        # The unified Gateway remains live; only its GLC capability is suspended.
        assert client.get("/health").json() == {"status": "ok"}


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


def test_rate_limit_refusal_is_stable() -> None:
    limiter = RateLimiter(default_mpm=1)
    assert limiter.check_message("webui", "u1") == (True, "")
    allowed, reason = limiter.check_message("webui", "u1")
    assert allowed is False
    assert reason == "messages limit 1/min exceeded for (webui, u1)"


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd"],
)
def test_ssrf_guard_rejects_internal_and_non_http_targets(url: str) -> None:
    with pytest.raises(HTTPException) as caught:
        prepare_safe_target(url)
    assert caught.value.status_code == 400


def test_policy_reload_is_atomic_on_invalid_replacement(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text("rules: [{tool: ping, action: allow}]\n", encoding="utf-8")
    engine = PolicyEngine.from_yaml(path)
    path.write_text("rules: [broken", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        engine.reload()
    verdict = engine.evaluate(
        {"name": "ping", "arguments": {}},
        {"channel": "webui", "trust_level": "owner_paired"},
    )
    assert verdict.action == "allow"


def test_pairing_repository_has_only_live_tables(tmp_path: Path) -> None:
    store = PairingStore(tmp_path / "pairings.sqlite")
    with store.database.connect() as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert names == {"pairings", "pending_codes"}


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
