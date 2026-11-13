"""C4 — /v1/chat must not leak raw provider error text to the client.

Before the fix, an upstream provider failure on an explicit-override
request (or the final "all providers unavailable" case) put the raw
`str(exception)` straight into the HTTPException detail returned to the
caller — SDK error bodies can carry things like account/org identifiers,
partial request echoes, or infra hints that shouldn't cross the trust
boundary. The fix: the client gets a generic message; the real detail
still lands in the audit/cost ledger via `db.log_call` (server-side only,
itself gated by the bearer-token auth on `/v1/calls`).
"""

from __future__ import annotations

from glc import providers as P


class _ExplodingProvider:
    model = "fake-model-x"
    capabilities: dict = {}

    async def chat(self, *args, **kwargs):
        raise P.ProviderError(
            "auth rejected for org_secret_internal_id=acct_deadbeef1234, key=sk-should-not-leak",
            status=403,
            retryable=False,
        )


def test_explicit_provider_failure_returns_generic_502(app_client, install_token):
    app_client.app.state.router.providers["gemini"] = _ExplodingProvider()

    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi", "provider": "gemini"},
    )
    assert r.status_code == 502
    body = r.json()
    assert body["detail"] == "upstream provider request failed"
    assert "acct_deadbeef1234" not in r.text
    assert "sk-should-not-leak" not in r.text


class _AlwaysUnavailableProvider:
    model = "fake-model-y"
    capabilities: dict = {}

    async def chat(self, *args, **kwargs):
        raise P.ProviderError(
            "rate limited, retry-after leaks internal quota_pool=prod-shard-7", status=429
        )


def test_all_providers_unavailable_returns_generic_503(app_client, install_token):
    """No explicit provider override: the router exhausts every candidate and
    hits the final `raise HTTPException(503, ...)` — that message must also
    be generic, not an f-string of every attempt's raw exception text."""
    rtr = app_client.app.state.router
    for name in list(rtr.providers):
        rtr.providers[name] = _AlwaysUnavailableProvider()
    # Force every provider straight to the non-retryable/explicit path isn't
    # needed here: with no override, ProviderError just gets skipped and
    # retried against the next candidate until none remain -> final 503.

    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi"},
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "all providers are currently unavailable"
    assert "quota_pool=prod-shard-7" not in r.text


class _FailsThenAllowsRetryProvider:
    """A retryable, non-explicit-override failure: the router should log the
    attempt and move on to the next candidate rather than raising."""

    model = "fake-model-fails"
    capabilities: dict = {}

    async def chat(self, *args, **kwargs):
        raise P.ProviderError(
            "internal token=sk-should-not-leak-either account=acct_9999", status=500, retryable=True
        )


class _SucceedsProvider:
    model = "fake-model-ok"
    capabilities: dict = {}

    async def chat(self, *args, **kwargs):
        return {
            "text": "hello",
            "model": self.model,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "tool_calls": [],
            "stop_reason": "end_turn",
            "reasoning_applied": False,
            "tool_call_dialect": "none",
        }


def test_fallback_then_success_does_not_leak_the_failed_providers_error_in_the_200(
    app_client, install_token
):
    """The gap the first pass of C4 missed: a request with NO explicit
    provider override that fails against provider A and then succeeds
    against provider B returns 200 with ChatResponse.attempted including
    provider A's failure — that list must not carry provider A's raw
    exception text either, since it rides into a response the client
    actually sees."""
    rtr = app_client.app.state.router
    rtr.providers["gemini"] = _FailsThenAllowsRetryProvider()
    rtr.providers["groq"] = _SucceedsProvider()
    rtr.order = ["gemini", "groq"]

    r = app_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {install_token}"},
        json={"prompt": "hi"},
    )
    assert r.status_code == 200
    assert "sk-should-not-leak-either" not in r.text
    assert "acct_9999" not in r.text
    body = r.json()
    assert body["provider"] == "groq"
    assert any(a["provider"] == "gemini" for a in body["attempted"])
