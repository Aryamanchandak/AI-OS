"""Orchestration behaviours beyond individual provider adapters."""

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


IMAGE_MESSAGES = [{'role': 'user', 'content': [
    {'type': 'text', 'text': 'Read this image'},
    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AAAA'}},
]}]


@pytest.mark.parametrize('selector', ['provider', 'profile'])
def test_image_is_rejected_for_a_text_only_selection(tmp_path: Path, selector: str) -> None:
    provider = SpyProvider('text-only')
    service, ledger = service_for(tmp_path, [provider])
    request = ChatRequest(messages=IMAGE_MESSAGES, **{selector: 'pin' if selector == 'profile' else provider.name})
    with pytest.raises(HTTPException) as caught:
        asyncio.run(service.chat(request))
    assert caught.value.status_code == 400
    assert 'vision-capable' in caught.value.detail
    assert provider.calls == 0
    assert len(ledger.recent()) == 1


def test_unpinned_image_uses_only_vision_capable_candidates(tmp_path: Path) -> None:
    from dataclasses import replace

    text, vision = SpyProvider('text-only'), SpyProvider('vision')
    vision.capabilities = replace(vision.capabilities, vision=True)
    service, _ = service_for(tmp_path, [text, vision])
    result = asyncio.run(service.chat(ChatRequest(messages=IMAGE_MESSAGES)))
    assert result['provider'] == 'vision'
    assert text.calls == 0 and vision.calls == 1
    assert vision.kwargs['messages'] == IMAGE_MESSAGES


def test_local_transcription_profile_dispatches_embedded_image(tmp_path: Path) -> None:
    from dataclasses import replace

    provider = SpyProvider('gemma', served_model='gemma4:12b')
    provider.capabilities = replace(provider.capabilities, vision=True)
    service, _ = service_for(tmp_path, [provider])
    service.pipeline.profiles.profiles = ProfileRegistry.from_yaml(
        Path(__file__).resolve().parents[1] / 'config/profiles.yaml')
    result = asyncio.run(service.chat(ChatRequest(messages=IMAGE_MESSAGES, profile='image-transcription-v1')))
    assert result['provider'] == 'gemma' and result['model'] == 'gemma4:12b'
    assert provider.kwargs['messages'] == IMAGE_MESSAGES
    assert provider.kwargs['model'] == 'gemma4:12b'
    assert provider.calls == 1
