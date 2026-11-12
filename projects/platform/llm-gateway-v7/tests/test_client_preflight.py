"""Unit tests for LLM.preflight() in client.py — mocked, no network/server.

client.py is a thin HTTP client with no existing test coverage (test_embed.py
and friends test main.py over an ASGI transport instead). These tests only
exercise preflight()'s own aggregation/fail-loud logic by stubbing chat()/
embed(), so they run fast and don't need `local`/`network` markers.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from client import LLM, GatewayPreflightError


def test_preflight_ok_when_both_paths_succeed(monkeypatch):
    llm = LLM()
    monkeypatch.setattr(llm, "chat", lambda *a, **kw: {"provider": "anthropic-sonnet", "model": "claude-sonnet-4-6"})
    monkeypatch.setattr(llm, "embed", lambda *a, **kw: {"provider": "ollama", "model": "nomic-embed-text", "dim": 768})

    checks = llm.preflight()

    assert checks["chat"] == {"ok": True, "provider": "anthropic-sonnet", "model": "claude-sonnet-4-6"}
    assert checks["embedding"] == {"ok": True, "provider": "ollama", "model": "nomic-embed-text", "dim": 768}


def test_preflight_raises_with_both_checks_when_chat_fails(monkeypatch):
    llm = LLM()

    def broken_chat(*a, **kw):
        raise RuntimeError("gateway 503")

    monkeypatch.setattr(llm, "chat", broken_chat)
    monkeypatch.setattr(llm, "embed", lambda *a, **kw: {"provider": "ollama", "model": "nomic-embed-text", "dim": 768})

    with pytest.raises(GatewayPreflightError) as exc_info:
        llm.preflight()

    assert exc_info.value.checks["chat"]["ok"] is False
    assert "gateway 503" in exc_info.value.checks["chat"]["error"]
    assert exc_info.value.checks["embedding"]["ok"] is True


def test_preflight_raises_when_embedding_profile_fails(monkeypatch):
    llm = LLM()
    monkeypatch.setattr(llm, "chat", lambda *a, **kw: {"provider": "anthropic-sonnet", "model": "claude-sonnet-4-6"})

    def broken_embed(*a, **kw):
        raise RuntimeError("profile 'chunker-v1' expected model 'nomic-embed-text' but got 'other-model'")

    monkeypatch.setattr(llm, "embed", broken_embed)

    with pytest.raises(GatewayPreflightError) as exc_info:
        llm.preflight(embedding_profile="chunker-v1")

    assert exc_info.value.checks["embedding"]["ok"] is False
    assert "chunker-v1" in exc_info.value.checks["embedding"]["error"]
