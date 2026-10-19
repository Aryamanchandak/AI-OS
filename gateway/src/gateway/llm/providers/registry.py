"""Provider construction and deterministic candidate selection."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from gateway.config import load_mapping
from gateway.llm.providers.base import Provider, ProviderCapabilities
from gateway.llm.providers.llm import LLMProvider

#: Claude and GPT take tools, images, structured output and a reasoning dial.
HOSTED = ProviderCapabilities(tools=True, vision=True, structured_output=True, reasoning=True)


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


def build_provider_registry(*, config_dir: Path) -> ProviderRegistry:
    timeout_s = float(load_mapping(config_dir / "providers.yaml").get("timeout_s", 180))
    providers: dict[str, Provider] = {}
    if key := os.getenv("OPENAI_API_KEY", "").strip():
        providers["openai"] = LLMProvider("openai", "openai", os.getenv("OPENAI_MODEL", "gpt-5.4-nano"), HOSTED,
                                          api_key=key, timeout_s=timeout_s)
    if key := os.getenv("ANTHROPIC_API_KEY", "").strip():
        providers["anthropic"] = LLMProvider("anthropic", "anthropic", os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"), HOSTED,
                                             api_key=key, timeout_s=timeout_s)
    raw = load_mapping(config_dir / "local_models.yaml")
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    for name, spec in (raw.get("models") or {}).items():
        model = os.getenv(spec.get("model_env", ""), spec["model"]) if spec.get("model_env") else spec["model"]
        # A model without a native tool API still gets the prompted fallback, so `tools` is always on.
        capabilities = ProviderCapabilities(tools=True, vision=bool(spec.get("vision")), reasoning=False, embeddings=True,
                                            max_context_tokens=int(spec.get("context_window", 32000)))
        providers[name] = LLMProvider(name, "ollama", model, capabilities, api_base=ollama_url, timeout_s=timeout_s,
                                      needs_think_false=bool(spec.get("needs_think_false")))
    return ProviderRegistry(providers)
