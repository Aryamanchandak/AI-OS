"""Orchestration behaviours that the provider and streaming suites do not cover."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import HTTPException
import pytest

from gateway.llm.models import ChatRequest
from gateway.llm.profiles import ProfileRegistry
from gateway.llm.providers.base import ProviderResult, ProviderUsage

from test_llm import FakeProvider, service_for


class SpyProvider(FakeProvider):
    def __init__(self, name: str, *, served_model: str | None = None) -> None:
        super().__init__(name)
        self.served_model = served_model or self.model
        self.kwargs: dict[str, Any] = {}

    async def chat(self, **kwargs: Any) -> ProviderResult:
        self.calls += 1
        self.kwargs = kwargs
        return ProviderResult(provider=self.name, model=self.served_model, text="ok",
                              usage=ProviderUsage(10, 2))


def test_pin_mismatch_surfaces_its_own_message_not_a_generic_503(tmp_path: Path) -> None:
    provider = SpyProvider("pinned", served_model="actually-served")
    service, _ = service_for(tmp_path, [provider])
    service.pipeline.profiles.profiles = ProfileRegistry(
        {"chat": {"pin": {"provider": "pinned", "model": "promised-model"}}, "embedding": {}})

    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.chat(ChatRequest(prompt="hi", profile="pin")))

    # Previously this was swallowed into `attempts` and re-surfaced as
    # "all providers unavailable", which told the operator nothing.
    assert caught.value.status_code == 500
    assert "expected model 'promised-model'" in str(caught.value.detail)
    assert "all providers unavailable" not in str(caught.value.detail)


def test_cache_system_reaches_the_provider_instead_of_being_ignored(tmp_path: Path) -> None:
    provider = SpyProvider("solo")
    service, _ = service_for(tmp_path, [provider])
    asyncio.run(service.chat(ChatRequest(prompt="hi", system="preamble", cache_system=True)))
    assert provider.kwargs["cache_system"] is True


def test_cache_system_defaults_to_off(tmp_path: Path) -> None:
    provider = SpyProvider("solo")
    service, _ = service_for(tmp_path, [provider])
    asyncio.run(service.chat(ChatRequest(prompt="hi")))
    assert provider.kwargs["cache_system"] is False
