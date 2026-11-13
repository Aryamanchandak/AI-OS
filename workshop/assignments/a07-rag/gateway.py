"""The only door to a model. Every layer imports `LLM` and `embed` from here.

A deliberately small gateway: one class, one provider protocol (the
OpenAI-compatible `/chat/completions` endpoint that OpenAI, Gemini,
Anthropic, Groq, Together and OpenRouter all serve), and one ledger line
per call in `state/llm_calls.jsonl`. No layer talks to a provider itself.

Configure it in `.env`:
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
or leave those out and set one of the well-known keys listed in
`_KNOWN_PROVIDERS`; the first one found is used.

Embeddings use the same provider's `/embeddings` endpoint. Override with
EMBED_API_KEY, EMBED_BASE_URL and EMBED_MODEL when the chat provider has no
embedding model. The embedding model must not change once an index exists:
vectors from two models cannot be compared.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

from paths import ROOT, STATE_DIR

load_dotenv(ROOT / ".env")

LEDGER_PATH = STATE_DIR / "llm_calls.jsonl"
TIMEOUT_SECONDS = 120

# (key variable, base URL, default model)
_KNOWN_PROVIDERS = [
    ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    ("OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4.1-mini"),
    ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1", "claude-haiku-4-5"),
    ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
]

# Providers that serve embeddings: (key variable, base URL, default model)
_KNOWN_EMBEDDERS = [
    ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-embedding-001"),
    ("OPENAI_API_KEY", "https://api.openai.com/v1", "text-embedding-3-small"),
]


def _settings() -> tuple[str, str, str]:
    """(api key, base URL, model) from the environment."""
    if key := os.getenv("LLM_API_KEY"):
        base = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base or not model:
            raise RuntimeError("LLM_API_KEY is set, so LLM_BASE_URL and LLM_MODEL must be set too.")
        return key, base.rstrip("/"), model
    for var, base, model in _KNOWN_PROVIDERS:
        if key := os.getenv(var):
            return key, base, os.getenv("LLM_MODEL") or model
    names = ", ".join(v for v, _, _ in _KNOWN_PROVIDERS)
    raise RuntimeError(f"No model key found. Put LLM_API_KEY or one of {names} in .env.")


def _embed_settings() -> tuple[str, str, str]:
    """(api key, base URL, model) for embeddings."""
    if key := os.getenv("EMBED_API_KEY"):
        base = os.getenv("EMBED_BASE_URL")
        model = os.getenv("EMBED_MODEL")
        if not base or not model:
            raise RuntimeError("EMBED_API_KEY is set, so EMBED_BASE_URL and EMBED_MODEL must be set too.")
        return key, base.rstrip("/"), model
    for var, base, model in _KNOWN_EMBEDDERS:
        if key := os.getenv(var):
            return key, base, os.getenv("EMBED_MODEL") or model
    names = ", ".join(v for v, _, _ in _KNOWN_EMBEDDERS)
    raise RuntimeError(f"No embedding key found. Put EMBED_API_KEY or one of {names} in .env.")


def _request_body(
    model: str,
    prompt: str,
    system: str | None,
    tools: list[dict] | None,
    tool_choice: str | None,
    response_format: dict | None,
    temperature: float,
    max_tokens: int,
) -> dict:
    """Translate the agent's call into the chat-completions wire shape."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
        if tool_choice:
            body["tool_choice"] = tool_choice
    if response_format:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_format.get("name", "Output"),
                "schema": response_format["schema"],
            },
        }
    return body


def _parse_reply(data: dict, wants_json: bool) -> dict:
    """Turn the provider's reply into {text, tool_calls, parsed, usage}."""
    message = data["choices"][0]["message"]
    text = message.get("content") or ""
    tool_calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        tool_calls.append({
            "name": fn.get("name", ""),
            "arguments": json.loads(fn.get("arguments") or "{}"),
        })
    parsed = json.loads(text) if wants_json and text.strip() else None
    return {
        "text": text,
        "tool_calls": tool_calls,
        "parsed": parsed,
        "usage": data.get("usage") or {},
    }


def _log_call(model: str, latency_ms: int, usage: dict, error: str | None) -> None:
    """One line per call: when, which model, how long, how many tokens. No prompts."""
    row = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "latency_ms": latency_ms,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "error": error,
    }
    LEDGER_PATH.parent.mkdir(exist_ok=True)
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(row) + "\n")


class LLM:
    """`LLM().chat(...)` returns a dict with `text`, `tool_calls`, `parsed`, `usage`."""

    def chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        cache_system: bool | None = None,  # accepted for callers; this gateway does not cache
    ) -> dict:
        key, base, model = _settings()
        body = _request_body(
            model, prompt, system, tools, tool_choice, response_format, temperature, max_tokens
        )
        t0 = time.perf_counter()
        error: str | None = None
        usage: dict = {}
        try:
            r = httpx.post(
                f"{base}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {key}"},
                timeout=TIMEOUT_SECONDS,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"{model} returned HTTP {r.status_code}: {r.text[:300]}")
            reply = _parse_reply(r.json(), wants_json=response_format is not None)
            usage = reply["usage"]
            return reply
        except Exception as e:
            error = type(e).__name__
            raise
        finally:
            _log_call(model, int((time.perf_counter() - t0) * 1000), usage, error)


def embed(text: str, task_type: str = "retrieval_document") -> dict:
    """Embedding for `text`. Returns {embedding, dim, model}.

    `task_type` is accepted for callers that distinguish documents from
    queries; the OpenAI-compatible endpoint has no such switch, so both use
    the same model.
    """
    key, base, model = _embed_settings()
    t0 = time.perf_counter()
    error: str | None = None
    usage: dict = {}
    try:
        r = httpx.post(
            f"{base}/embeddings",
            json={"model": model, "input": text},
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT_SECONDS,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"{model} returned HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        usage = data.get("usage") or {}
        vector = data["data"][0]["embedding"]
        return {"embedding": vector, "dim": len(vector), "model": model}
    except Exception as e:
        error = type(e).__name__
        raise
    finally:
        _log_call(model, int((time.perf_counter() - t0) * 1000), usage, error)


__all__ = ["LLM", "embed"]
