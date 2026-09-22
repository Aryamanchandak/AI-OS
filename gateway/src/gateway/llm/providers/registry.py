"""Provider construction and deterministic candidate selection."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
from typing import Any

import httpx
import yaml

from gateway.llm.providers.anthropic import AnthropicProvider
from gateway.llm.providers.base import Provider
from gateway.llm.providers.capabilities import resolve as capability_overrides
from gateway.llm.providers.gemini import GeminiProvider
from gateway.llm.providers.ollama import OllamaProvider
from gateway.llm.providers.openai import OpenAIProvider
from gateway.llm.providers.openai_compatible import OpenAICompatibleProvider


COMPATIBLE: dict[str, tuple[str, str, str]] = {
    "groq": ("GROQ_API_KEY", "GROQ_MODEL", "https://api.groq.com/openai/v1"),
    "cerebras": ("CEREBRAS_API_KEY", "CEREBRAS_MODEL", "https://api.cerebras.ai/v1"),
    "nvidia": ("NVIDIA_API_KEY", "NVIDIA_MODEL", "https://integrate.api.nvidia.com/v1"),
    "openrouter": ("OPEN_ROUTER_API_KEY", "OPENROUTER_MODEL", "https://openrouter.ai/api/v1"),
    "github": ("GITHUB_ACCESS_TOKEN", "GITHUB_MODEL", "https://models.inference.ai.azure.com"),
}
DEFAULT_MODELS = {"groq": "openai/gpt-oss-120b", "cerebras": "zai-glm-4.7", "nvidia": "deepseek-ai/deepseek-v3.2", "openrouter": "nvidia/nemotron-3-super-120b-a12b:free", "github": "openai/gpt-4.1-mini"}


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
        for name, variable, default in (("openai-cheap", "OPENAI_CHEAP_MODEL", "gpt-5.4-nano"), ("openai-mini", "OPENAI_MINI_MODEL", "gpt-5.4-mini"), ("openai-pro", "OPENAI_PRO_MODEL", "gpt-5.5")):
            providers[name] = OpenAIProvider(name, key, os.getenv(variable, default), client)
    if key := os.getenv("ANTHROPIC_API_KEY", "").strip():
        for name, variable, default in (("anthropic-haiku", "ANTHROPIC_HAIKU_MODEL", "claude-haiku-4-5"), ("anthropic-sonnet", "ANTHROPIC_SONNET_MODEL", "claude-sonnet-4-6"), ("anthropic-opus", "ANTHROPIC_OPUS_MODEL", "claude-opus-4-8")):
            providers[name] = AnthropicProvider(name, key, os.getenv(variable, default), client)
    gemini_keys = [os.getenv(f"GEMINI_API_KEY_{i}", "").strip() for i in range(1, 11)]
    gemini_keys = [x for x in gemini_keys if x] or ([os.getenv("GEMINI_API_KEY", "").strip()] if os.getenv("GEMINI_API_KEY", "").strip() else [])
    for index, key in enumerate(gemini_keys, 1):
        name = f"gemini_{index}"
        providers[name] = GeminiProvider(name, key, os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), client)
    for name, (key_var, model_var, url) in COMPATIBLE.items():
        if key := os.getenv(key_var, "").strip():
            providers[name] = OpenAICompatibleProvider(name, key, os.getenv(model_var, DEFAULT_MODELS[name]), url, client)
    raw = yaml.safe_load((config_dir / "local_models.yaml").read_text(encoding="utf-8")) or {}
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
