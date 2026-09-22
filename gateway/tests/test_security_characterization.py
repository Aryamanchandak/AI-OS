"""Characterization tests ported from GLC's allowlist/trust/pairing/rate-limit
test files (Work Package C), plus route-level coverage the Plan 03
verification report flagged as missing: the kill endpoint's loopback
rejection path, and that audit-fail-closed/fail-open actually holds state,
not just a status code.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.app.main import create_app
from gateway.security.allowlists import Allowlist
from gateway.security.pairing import CODE_TTL_SECONDS, PairingStore
from gateway.security.rate_limits import RateLimiter
from gateway.security.trust import classify

# --- Allowlist -------------------------------------------------------------

CONFIG = {
    "defaults": {"allowed_senders": [], "mention_only_in_public": True},
    "channels": {
        "webui": {"enabled": True},
        "telegram": {"enabled": False},
    },
}


def test_owner_in_dm_is_allowed() -> None:
    ok, _ = Allowlist(CONFIG).allowed(
        "webui", "owner-1", owner_ids=["owner-1"], is_public_channel=False, was_mentioned=False
    )
    assert ok


def test_unknown_sender_in_dm_is_denied_by_default() -> None:
    ok, why = Allowlist(CONFIG).allowed(
        "webui", "stranger-1", owner_ids=["owner-1"], is_public_channel=False, was_mentioned=False
    )
    assert ok is False
    assert "allowed_senders" in why


def test_owner_in_public_without_mention_is_denied() -> None:
    ok, why = Allowlist(CONFIG).allowed(
        "webui", "owner-1", owner_ids=["owner-1"], is_public_channel=True, was_mentioned=False
    )
    assert ok is False
    assert "mention" in why.lower()


def test_owner_in_public_with_mention_is_allowed() -> None:
    ok, _ = Allowlist(CONFIG).allowed(
        "webui", "owner-1", owner_ids=["owner-1"], is_public_channel=True, was_mentioned=True
    )
    assert ok


def test_disabled_channel_blocks_owner() -> None:
    # telegram is disabled in this fixture config; even the owner is
    # blocked until the operator enables the channel in channels.yaml.
    ok, why = Allowlist(CONFIG).allowed("telegram", "owner-1", owner_ids=["owner-1"])
    assert ok is False
    assert "disabled" in why


def test_unlisted_channel_defaults_enabled() -> None:
    """A channel absent from `channels:` must default `enabled: True`,
    matching the original `_entry()`'s default — only an explicit
    `enabled: false` in `channels.yaml` should block a channel."""
    ok, _ = Allowlist({"defaults": {}, "channels": {}}).allowed(
        "some-new-channel", "owner-1", owner_ids=["owner-1"]
    )
    assert ok


# --- Trust classification ---------------------------------------------------


def test_trust_level_unknown_is_untrusted(tmp_path: Path) -> None:
    store = PairingStore(tmp_path / "p.sqlite")
    assert classify(store, "telegram", "no-such-user") == "untrusted"


def test_trust_level_owner_paired(tmp_path: Path) -> None:
    store = PairingStore(tmp_path / "p.sqlite")
    store.force_pair_owner("matrix", "owner-1", "owner")
    assert classify(store, "matrix", "owner-1") == "owner_paired"


def test_trust_level_user_paired(tmp_path: Path) -> None:
    store = PairingStore(tmp_path / "p.sqlite")
    code, _ = store.issue_code("slack", "U1", "user")
    store.confirm_code(code)
    assert classify(store, "slack", "U1") == "user_paired"


# --- Pairing -----------------------------------------------------------------


def test_issue_code_is_six_digits(tmp_path: Path) -> None:
    store = PairingStore(tmp_path / "p.sqlite")
    code, expires_at = store.issue_code("telegram", "42", "me")
    assert len(code) == 6 and code.isdigit()
    assert expires_at > time.time()


def test_confirm_creates_pairing(tmp_path: Path) -> None:
    store = PairingStore(tmp_path / "p.sqlite")
    code, _ = store.issue_code("telegram", "42", "me", requested_trust_level="user_paired")
    record = store.confirm_code(code)
    assert record is not None
    assert record.trust_level == "user_paired"
    assert store.lookup("telegram", "42") is not None


def test_expired_code_is_rejected(tmp_path: Path) -> None:
    now = [1_000_000.0]
    store = PairingStore(tmp_path / "p.sqlite", clock=lambda: now[0])
    code, _ = store.issue_code("telegram", "42", "me")
    now[0] += CODE_TTL_SECONDS + 1
    assert store.confirm_code(code) is None


def test_unknown_code_returns_none(tmp_path: Path) -> None:
    store = PairingStore(tmp_path / "p.sqlite")
    assert store.confirm_code("000000") is None


def test_code_collision_replaces_pending(tmp_path: Path) -> None:
    store = PairingStore(tmp_path / "p.sqlite")
    code1, _ = store.issue_code("slack", "U1")
    code2, _ = store.issue_code("slack", "U1")
    # Two requests for the same user: latest pending wins.
    if code1 != code2:
        assert store.confirm_code(code2) is not None


# --- Rate limits --------------------------------------------------------------


def test_yaml_configuration_per_channel() -> None:
    limiter = RateLimiter(default_mpm=10, default_tpm=10)
    limiter.configure(
        {
            "defaults": {"rate_limits": {"messages_per_minute": 10, "tool_calls_per_minute": 10}},
            "channels": {"telegram": {"rate_limits": {"messages_per_minute": 1}}},
        }
    )
    assert limiter.check_message("telegram", "1")[0]
    assert limiter.check_message("telegram", "1")[0] is False
    # Other channels still have the default cap.
    for _ in range(5):
        assert limiter.check_message("discord", "1")[0]


def test_tool_calls_separate_from_messages() -> None:
    limiter = RateLimiter(default_mpm=1, default_tpm=1)
    assert limiter.check_message("x", "1")[0]
    assert limiter.check_tool_call("x", "1")[0]


# --- Route-level: kill loopback guard, and fail-closed/fail-open state -------


@pytest.fixture
def glc_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path | str]:
    policy = tmp_path / "policy.yaml"
    policy.write_text("rules:\n  - {tool: ping, action: allow}\n", encoding="utf-8")
    channels = tmp_path / "channels.yaml"
    channels.write_text("defaults: {}\nchannels: {}\n", encoding="utf-8")
    values: dict[str, Path | str] = {
        "policy": policy,
        "audit": tmp_path / "audit.sqlite",
        "token": "install-token-for-tests",
    }
    token_file = tmp_path / "install_token"
    token_file.write_text(str(values["token"]), encoding="utf-8")
    monkeypatch.setenv("GLC_POLICY_YAML", str(policy))
    monkeypatch.setenv("GLC_CHANNELS_YAML", str(channels))
    monkeypatch.setenv("GLC_AUDIT_DB", str(values["audit"]))
    monkeypatch.setenv("GLC_PAIRING_DB", str(tmp_path / "pairings.sqlite"))
    monkeypatch.setenv("GLC_GATEWAY_DB", str(tmp_path / "gateway.sqlite"))
    monkeypatch.setenv("GLC_INSTALL_TOKEN_FILE", str(token_file))
    return values


def test_kill_from_non_loopback_is_rejected_without_the_override(
    glc_environment: dict[str, Path | str],
) -> None:
    """The kill endpoint's default posture must actually reject a
    non-loopback caller — every other kill test in this suite sets
    `GLC_KILL_ALLOW_REMOTE=1`, which never exercises the guard itself."""
    headers = {"Authorization": f"Bearer {glc_environment['token']}"}
    with TestClient(create_app(token="gateway-token")) as client:
        response = client.post("/v1/control/kill", headers=headers)
    # TestClient's synthetic client host is not loopback, so the guard
    # must fire.
    assert response.status_code == 403
    assert "loopback" in response.json()["detail"]


def test_audit_unavailable_blocks_pair_confirm_and_kill_without_side_effects(
    glc_environment: dict[str, Path | str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision #4 (Plan 03) requires a deliberate audit fail-open/closed
    policy for control actions, not whatever an unhandled exception leaves
    behind. Mutating actions must fail closed: refuse the effect, not just
    return an error status after already applying it."""
    monkeypatch.setenv("GLC_KILL_ALLOW_REMOTE", "1")
    headers = {"Authorization": f"Bearer {glc_environment['token']}"}
    app = create_app(token="gateway-token")
    with TestClient(app, raise_server_exceptions=False) as client:
        control = app.state.container.control
        control.audit.database.path = Path(str(glc_environment["audit"])).parent  # a directory: unopenable

        pair_response = client.post(
            "/v1/control/pair", headers=headers, json={"channel": "t", "channel_user_id": "1"}
        )
        assert pair_response.status_code == 503
        with app.state.container.pairings.database.connect() as connection:
            pending = connection.execute("SELECT COUNT(*) FROM pending_codes").fetchone()[0]
        assert pending == 0, "a rejected pair request must not leave a pending code behind"

        reload_response = client.post("/v1/control/reload-policy", headers=headers)
        assert reload_response.status_code == 503
        verdict = control.policy.evaluate({"name": "ping"}, {"trust_level": "owner_paired"})
        assert verdict.action == "allow", "a rejected reload must not have swapped the policy"

        kill_response = client.post("/v1/control/kill", headers=headers)
        assert kill_response.status_code == 503
        assert control.glc_enabled is True, "a rejected kill must not have suspended GLC"

        # Presence is a read, not a security decision: it stays available
        # even while the audit log cannot record its (best-effort) entry.
        presence_response = client.get("/v1/control/presence", headers=headers)
        assert presence_response.status_code == 200


def test_sighup_reload_failure_does_not_crash_the_process(
    glc_environment: dict[str, Path | str],
) -> None:
    """A malformed policy.yaml on SIGHUP must be caught and logged, not
    raised out of the signal handler — matching GLC's original behavior.
    Exercised through the reload path directly rather than sending a real
    signal, since pytest's own process is not an appropriate target."""
    from gateway.app.lifespan import _reload_policy_on_sighup

    app = create_app(token="gateway-token")
    with TestClient(app):
        container = app.state.container
        Path(str(glc_environment["policy"])).write_text("rules: [broken", encoding="utf-8")
        _reload_policy_on_sighup(container)  # must not raise
        # The bad file must not have been swapped in.
        verdict = container.policy.evaluate({"name": "ping"}, {"trust_level": "owner_paired"})
        assert verdict.action == "allow"
        # SIGHUP reloads (success or failure) are deliberately not audited
        # (see lifespan._reload_policy_on_sighup's docstring) — confirm no
        # record leaked through.
        rows = container.audit.query()
        assert not any(row["event_type"] == "policy_reloaded" for row in rows)
