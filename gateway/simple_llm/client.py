"""Direct synchronous calls to OpenAI, Anthropic or local Ollama."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from openai import OpenAI


class LLM:
    """Reads this folder's .env; explicit shell variables take precedence.

    Use as a context manager to close the provider connections when finished.
    Calls go directly to the chosen provider; failures propagate to the caller.
    """

    def __init__(self, *, env_file: str | Path | None = None, timeout: float = 180) -> None:
        load_dotenv(env_file or Path(__file__).with_name(".env"), override=False)
        self.timeout = timeout
        self._clients: dict[str, Any] = {}

    def _client(self, provider: str) -> Any:
        if provider not in {"openai", "anthropic", "ollama"}:
            raise ValueError("provider must be openai, anthropic or ollama")
        if provider not in self._clients:
            options: dict[str, Any] = {"timeout": self.timeout, "max_retries": 2}
            if provider == "ollama":
                options.update(api_key="ollama", base_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/v1")
            else:
                key_name = f"{provider.upper()}_API_KEY"
                key = os.getenv(key_name, "").strip()
                if not key:
                    raise ValueError(f"Set {key_name} in simple_llm/.env or your environment")
                options["api_key"] = key
            self._clients[provider] = anthropic.Anthropic(**options) if provider == "anthropic" else OpenAI(**options)
        return self._clients[provider]

    def chat(
        self, prompt: str | None = None, *, messages: list[dict[str, Any]] | None = None,
        system: str | None = None, provider: str | None = None, model: str | None = None,
        max_tokens: int = 2048, temperature: float | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return text, optional schema-validated JSON, provider and model.

        Supply either prompt or messages. For JSON output, pass a JSON Schema
        as schema. No automatic repair call is made if validation fails.
        """
        if (prompt is None) == (messages is None):
            raise ValueError("Supply exactly one of prompt or messages")
        if not max_tokens > 0:
            raise ValueError("max_tokens must be positive")
        if schema is not None:
            Draft202012Validator.check_schema(schema)
        provider = provider or os.getenv("LLM_PROVIDER", "anthropic")
        client = self._client(provider)
        defaults = {"openai": "gpt-5.4-nano", "anthropic": "claude-haiku-4-5", "ollama": "gemma4:12b"}
        model = model or os.getenv(f"{provider.upper()}_MODEL") or defaults[provider]
        turns = [dict(message) for message in messages] if messages is not None else [{"role": "user", "content": prompt}]
        options: dict[str, Any] = {"model": model}
        if temperature is not None:
            options["temperature"] = temperature
        if provider == "anthropic":
            systems = ([system] if system else []) + [str(m["content"]) for m in turns if m["role"] == "system"]
            options.update(messages=[m for m in turns if m["role"] != "system"], max_tokens=max_tokens)
            if systems:
                options["system"] = "\n\n".join(systems)
            if schema is not None:
                options["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
            reply = client.messages.create(**options)
            text = "".join(block.text for block in reply.content if block.type == "text")
        else:
            if system:
                turns.insert(0, {"role": "system", "content": system})
            options.update(messages=turns)
            options["max_completion_tokens" if provider == "openai" else "max_tokens"] = max_tokens
            if schema is not None:
                options["response_format"] = {"type": "json_schema", "json_schema": {"name": "result", "strict": True, "schema": schema}}
            reply = client.chat.completions.create(**options)
            text = reply.choices[0].message.content
            if text is None:
                raise RuntimeError("Provider returned no text (possibly a refusal)")
        parsed = json.loads(text) if schema is not None else None
        if schema is not None:
            Draft202012Validator(schema).validate(parsed)
        return {"text": text, "parsed": parsed, "provider": provider, "model": reply.model}

    def embed(self, text: str, *, provider: str = "ollama", model: str | None = None) -> dict[str, Any]:
        """Return one vector. Local nomic-embed-text is the default; OpenAI is optional."""
        if provider not in {"openai", "ollama"}:
            raise ValueError("Embeddings require openai or ollama")
        model = model or (os.getenv("EMBEDDING_MODEL", "nomic-embed-text") if provider == "ollama" else "text-embedding-3-small")
        reply = self._client(provider).embeddings.create(model=model, input=text)
        vector = reply.data[0].embedding
        if not vector:
            raise RuntimeError("Provider returned an empty embedding")
        return {"embedding": vector, "dim": len(vector), "provider": provider, "model": model}

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    def __enter__(self) -> LLM:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
