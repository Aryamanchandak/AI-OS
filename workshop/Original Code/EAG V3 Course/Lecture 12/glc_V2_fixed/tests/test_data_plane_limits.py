"""C5 — rate limiting and a cost circuit breaker on the HTTP data plane.

Before this, `/v1/chat`, `/v1/vision`, `/v1/embed`, `/v1/speak`,
`/v1/transcribe` had auth (Phase 4) but nothing bounding how many requests a
caller could fire or how much they could spend — invariant 8 ("every run
must have hard limits on ... cost") was unenforced. These tests exercise
the limiter and breaker directly (unit-level, no network) and end-to-end
through `/v1/status` (auth-gated, cheap, deterministic body) so the
router-level dependency wiring itself is proven, not just the underlying
class.
"""

from __future__ import annotations

from glc.security.data_plane_limits import TokenBucket, enforce_cost_budget


def test_token_bucket_allows_up_to_capacity_then_blocks():
    bucket = TokenBucket(capacity=3, refill_per_second=0.0)  # no refill mid-test
    key = "1.2.3.4"
    assert bucket.allow(key) == (True, "")
    assert bucket.allow(key) == (True, "")
    assert bucket.allow(key) == (True, "")
    ok, why = bucket.allow(key)
    assert ok is False
    assert "rate limit exceeded" in why


def test_token_bucket_keys_are_independent():
    bucket = TokenBucket(capacity=1, refill_per_second=0.0)
    assert bucket.allow("caller-a") == (True, "")
    ok, _ = bucket.allow("caller-a")
    assert ok is False
    # a different caller has its own budget, unaffected by caller-a's use
    assert bucket.allow("caller-b") == (True, "")


def test_rate_limit_trips_429_over_http(app_client, install_token, monkeypatch):
    import glc.security.data_plane_limits as dpl

    monkeypatch.setenv("GLC_DATA_PLANE_RPM", "2")
    dpl.reset_for_tests()
    h = {"Authorization": f"Bearer {install_token}"}
    r1 = app_client.get("/v1/status", headers=h)
    r2 = app_client.get("/v1/status", headers=h)
    r3 = app_client.get("/v1/status", headers=h)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert "rate limit" in r3.json()["detail"]


def test_cost_breaker_disabled_at_zero_ceiling(monkeypatch):
    monkeypatch.setenv("GLC_DAILY_COST_CEILING_USD", "0")
    enforce_cost_budget()  # must not raise


def test_cost_breaker_trips_when_todays_spend_meets_ceiling(monkeypatch):
    import pytest
    from fastapi import HTTPException

    from glc import db

    # This test never spins up the app (no `app_client` fixture), so the
    # lifespan hook that normally calls db.init() never runs — do it
    # directly so `calls` exists in this test's isolated GLC_GATEWAY_DB.
    db.init()

    monkeypatch.setenv("GLC_DAILY_COST_CEILING_USD", "0.01")
    # groq is priced (not one of the $0 free-tier providers), so a real
    # token count here produces nonzero spend via glc.pricing.estimate_usd.
    db.log_call(provider="groq", model="x", input_tokens=1_000_000, output_tokens=0, status="ok")

    with pytest.raises(HTTPException) as exc:
        enforce_cost_budget()
    assert exc.value.status_code == 503
    assert "circuit breaker" in exc.value.detail


def test_cost_breaker_end_to_end_over_http(app_client, install_token, monkeypatch):
    from glc import db

    monkeypatch.setenv("GLC_DAILY_COST_CEILING_USD", "0.01")
    db.log_call(provider="groq", model="x", input_tokens=1_000_000, output_tokens=0, status="ok")

    r = app_client.get("/v1/status", headers={"Authorization": f"Bearer {install_token}"})
    assert r.status_code == 503
    assert "circuit breaker" in r.json()["detail"]
