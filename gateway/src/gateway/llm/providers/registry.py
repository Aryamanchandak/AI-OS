"""Provider construction and deterministic candidate selection."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
from typing import Any

import httpx

from gateway.config import load_mapping
from gateway.llm.providers.anthropic import AnthropicProvider
from gateway.llm.providers.base import Provider
from gateway.llm.providers.capabilities import resolve as capability_overrides
from gateway.llm.providers.ollama import OllamaProvider
from gateway.llm.providers.openai import OpenAIProvider


class ProviderRegistry:
    def __init__(self, providers: dict[str, Provider], order: list[str] | None = None) -> None:
        self.providers = providers
        self.order = [x for x in (order or list(providers)) if x in providers]

    def candidates(self, explicit: str | None = None) -> list[Provider]:
        if explicit:
            return [self.providers[explicit]] if explicit in self.providers else []
        return [self.providers[name] for name in self.order]

    def get(self, name: str) -> Provider | None:
        return self.providers.get(name)

    def diagnostics(self) -> dict[str, Any]:
        return {name: {"model": p.model, **p.capabilities.as_dict()} for name, p in self.providers.items()}


def build_provider_registry(client: httpx.AsyncClient, *, config_dir: Path) -> ProviderRegistry:
    providers: dict[str, Provider] = {}
    if key := os.getenv("OPENAI_API_KEY", "").strip():
        providers["openai"] = OpenAIProvider("openai", key, os.getenv("OPENAI_MODEL", "gpt-5.4-nano"), client)
    if key := os.getenv("ANTHROPIC_API_KEY", "").strip():
        providers["anthropic"] = AnthropicProvider("anthropic", key, os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"), client)
    raw = load_mapping(config_dir / "local_models.yaml")
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    for name, spec in (raw.get("models") or {}).items():
        model = os.getenv(spec.get("model_env", ""), spec["model"]) if spec.get("model_env") else spec["model"]
        providers[name] = OllamaProvider(name, model, client, ollama_url, vision=bool(spec.get("vision")), context_window=int(spec.get("context_window", 32000)), needs_think_false=bool(spec.get("needs_think_false")))
    # Bake per-model capability overrides into each instance, so `/capabilities`
    # reports what the configured model can do rather than a class-level default.
    for name, provider in providers.items():
        resolved = capability_overrides(name, provider.model, provider.capabilities)
        if isinstance(provider, OllamaProvider):
            # `local_models.yaml` states vision per model; that operator-declared
            # value outranks the name-hint guess, exactly as in the legacy tree.
            resolved = replace(resolved, vision=provider.capabilities.vision)
        provider.capabilities = resolved
    return ProviderRegistry(providers)
