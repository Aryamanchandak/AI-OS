"""Direct OpenAI client.

All LLM calls go straight to the OpenAI API via httpx.
Embeddings use local Ollama (nomic-embed-text).
ensure_gateway() is a no-op kept for call-site compatibility.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional

import httpx

_API_KEY = os.environ.get("OPENAI_API_KEY", "")
_BASE = "https://api.openai.com/v1"
_CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
_EMBED_MODEL = os.getenv("NOMIC_EMBED_MODEL", "nomic-embed-text")
_OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_EMBED_DIM = 768


def ensure_gateway() -> None:
    """No-op kept for call-site compatibility."""
    pass


# ── helpers ──────────────────────────────────────────────────────────────────

def _post_with_retry(url: str, headers: dict, body: dict, max_retries: int = 4) -> httpx.Response:
    """POST with exponential backoff on 429 rate-limit responses."""
    for attempt in range(max_retries + 1):
        r = httpx.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 429 or attempt == max_retries:
            return r
        try:
            msg = r.json()["error"]["message"]
            m = re.search(r"try again in (\d+\.?\d*)s", msg)
            wait = float(m.group(1)) + 1.0 if m else (2 ** attempt) * 5.0
        except Exception:
            wait = (2 ** attempt) * 5.0
        print(f"[gateway] 429 rate limit — sleeping {wait:.1f}s (attempt {attempt + 1}/{max_retries})")
        time.sleep(wait)
    return r  # unreachable but satisfies type checker


# ── LLM client ───────────────────────────────────────────────────────────────

class LLM:
    def chat(
        self,
        prompt: str = None,
        *,
        messages: Optional[list] = None,
        system: Any = None,
        tools: Optional[list] = None,
        tool_choice: Any = None,
        cache_system: Optional[bool] = None,  # accepted, ignored
        response_format: Any = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: Optional[str] = None,
        **_ignored,
    ) -> dict:
        m = model or _CHAT_MODEL

        # Build messages list
        if messages:
            out_messages = _translate_messages(messages, system)
        else:
            out_messages = []
            if system:
                out_messages.append({"role": "system", "content": system if isinstance(system, str) else str(system)})
            out_messages.append({"role": "user", "content": prompt or ""})

        body: dict[str, Any] = {
            "model": m,
            "messages": out_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            body["tools"] = _translate_tools(tools)
            if tool_choice == "none":
                body["tool_choice"] = "none"
            elif isinstance(tool_choice, dict):
                body["tool_choice"] = {"type": "function", "function": {"name": tool_choice.get("name", "")}}
            else:
                body["tool_choice"] = "auto"

        if response_format:
            rf = response_format if isinstance(response_format, dict) else {}
            schema = rf.get("schema") or rf.get("json_schema", {}).get("schema")
            if schema:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "response", "schema": schema},
                }
            elif rf.get("type") == "json_object":
                body["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {_API_KEY}",
            "Content-Type": "application/json",
        }

        r = _post_with_retry(f"{_BASE}/chat/completions", headers=headers, body=body)
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:400]}")

        d = r.json()
        choice = (d.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text = msg.get("content") or ""

        tool_calls_out = []
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            args = fn.get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"_raw": args}
            tool_calls_out.append({
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": args,
            })

        parsed = None
        if response_format and text:
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None

        return {"text": text, "parsed": parsed, "tool_calls": tool_calls_out}

    def embed(self, text: str, task_type: str = "retrieval_document") -> dict:
        return embed(text, task_type=task_type)


# ── helpers ──────────────────────────────────────────────────────────────────

def _translate_tools(tools: list) -> list:
    out = []
    for t in tools:
        d = t if isinstance(t, dict) else t.model_dump()
        out.append({
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d.get("description", ""),
                "parameters": d.get("input_schema") or {"type": "object", "properties": {}},
            },
        })
    return out


def _translate_messages(messages: list, system: Any = None) -> list:
    out = []
    if system:
        out.append({"role": "system", "content": system if isinstance(system, str) else str(system)})
    for m in messages:
        r = m.get("role")
        if r == "system":
            if not system:
                out.append({"role": "system", "content": m.get("content", "")})
            continue
        if r == "assistant" and m.get("tool_calls"):
            tcs = []
            for tc in m["tool_calls"]:
                args = tc.get("arguments") or {}
                if isinstance(args, dict):
                    args = json.dumps(args)
                tcs.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": args},
                })
            out.append({
                "role": "assistant",
                "content": m.get("content") or None,
                "tool_calls": tcs,
            })
            continue
        if r == "tool":
            content = m.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content)
            out.append({
                "role": "tool",
                "tool_call_id": m.get("tool_call_id", m.get("id", "")),
                "content": content,
            })
            continue
        out.append({"role": r, "content": m.get("content", "")})
    return out


# ── embedding ────────────────────────────────────────────────────────────────

def embed(text: str, task_type: str = "retrieval_document") -> dict:
    url = f"{_OLLAMA_BASE}/api/embeddings"
    r = httpx.post(url, json={"model": _EMBED_MODEL, "prompt": text}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Ollama embed {r.status_code}: {r.text[:200]}")
    vec = r.json().get("embedding") or []
    if not vec:
        raise RuntimeError(f"Ollama returned no embedding: {r.text[:200]}")
    return {"embedding": vec, "dim": len(vec), "model": _EMBED_MODEL}


def tts(text: str, voice: str = "alloy", model: str = "tts-1") -> bytes:
    """Convert text to speech via OpenAI TTS. Returns raw MP3 bytes."""
    headers = {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {"model": model, "input": text, "voice": voice}
    r = _post_with_retry(f"{_BASE}/audio/speech", headers=headers, body=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI TTS {r.status_code}: {r.text[:400]}")
    return r.content


__all__ = ["ensure_gateway", "LLM", "embed", "tts"]
