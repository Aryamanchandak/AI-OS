"""V7 embedding-profile tests. Run from llm_gatewayV7/:  uv run pytest -v tests/test_profiles.py

Profiles (embedders.PROFILES) pin a caller to one exact provider+model pair
instead of a bare provider name, and the gateway fails loud on any mismatch
rather than silently returning a different model's vectors. See
CHANGES_2026-07-27_preflight_and_profiles.md.

Same in-process ASGI pattern as test_embed.py — no running server required.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
load_dotenv(HERE.parent / ".env")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client():
    import main as M
    transport = httpx.ASGITransport(app=M.app)
    async with M.app.router.lifespan_context(M.app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            timeout=60,
        ) as c:
            yield c


@pytest.mark.local
@pytest.mark.asyncio
async def test_known_profile_resolves_to_pinned_provider_and_model(client):
    r = await client.post("/v1/embed", json={
        "text": "the quick brown fox",
        "profile": "chunker-v1",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["provider"] == "ollama"
    assert d["model"] == "nomic-embed-text"
    assert d["dim"] == 768
    assert d["profile"] == "chunker-v1"


@pytest.mark.asyncio
async def test_unknown_profile_rejected(client):
    r = await client.post("/v1/embed", json={
        "text": "hello",
        "profile": "no-such-profile",
    })
    assert r.status_code == 400, r.text
    assert "no-such-profile" in r.text


@pytest.mark.asyncio
async def test_profile_and_conflicting_provider_rejected(client):
    r = await client.post("/v1/embed", json={
        "text": "hello",
        "profile": "chunker-v1",
        "provider": "gemini",
    })
    assert r.status_code == 400, r.text
    assert "chunker-v1" in r.text and "gemini" in r.text


@pytest.mark.local
@pytest.mark.asyncio
async def test_profile_model_mismatch_fails_loud(client, monkeypatch):
    """If a profile's pinned model ever stops matching what the provider
    actually returns, the gateway must error, not silently pass through a
    different vector space."""
    import embedders as E
    monkeypatch.setitem(
        E.PROFILES, "chunker-v1", {"provider": "ollama", "model": "not-the-real-model", "dim": 768}
    )
    r = await client.post("/v1/embed", json={
        "text": "hello",
        "profile": "chunker-v1",
    })
    assert r.status_code == 500, r.text
    assert "not-the-real-model" in r.text


@pytest.mark.local
@pytest.mark.asyncio
async def test_profile_dim_mismatch_fails_loud(client, monkeypatch):
    """Same as above but the model name matches and only `dim` diverges —
    the model-name check alone would miss a re-pulled/reconfigured model
    that returns a different width under the same name."""
    import embedders as E
    monkeypatch.setitem(
        E.PROFILES, "chunker-v1", {"provider": "ollama", "model": "nomic-embed-text", "dim": 1536}
    )
    r = await client.post("/v1/embed", json={
        "text": "hello",
        "profile": "chunker-v1",
    })
    assert r.status_code == 500, r.text
    assert "1536" in r.text


@pytest.mark.asyncio
async def test_embedders_endpoint_lists_profiles(client):
    r = await client.get("/v1/embedders")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["profiles"]["chunker-v1"] == {
        "provider": "ollama", "model": "nomic-embed-text", "dim": 768,
    }


@pytest.mark.local
@pytest.mark.asyncio
async def test_call_log_records_which_profile_was_used(client):
    """A profile-based call must be distinguishable from a plain provider=
    call in the call log — otherwise `/v1/calls` can't answer "was this
    request using the pinned chunker profile or a bare provider name?"."""
    await client.post("/v1/embed", json={"text": "log me", "profile": "chunker-v1"})
    r = await client.get("/v1/calls", params={"limit": 1})
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["profile"] == "chunker-v1"
