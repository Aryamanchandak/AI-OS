"""Prompted tool-calling fallback for Ollama models with no native tool API.

Most local models cannot be handed an OpenAI-style `tools` array. Rather than
losing tool calling entirely on those models, the tool catalogue is described in
the system prompt and the reply is parsed back out. Ported from
`_prompted_tool_system` / `_parse_prompted_tool_call` in
`glc_v5/glc/providers.py:1215`.
"""

from __future__ import annotations

import json
import re
from typing import Any
import uuid

from gateway.llm.providers.content import tool_specs

#: Model families whose Ollama builds accept a native `tools` array.
NATIVE_TOOL_MODELS = (
    "llama3.1", "llama3.2", "llama3.3", "qwen2.5", "qwen3",
    "mistral-nemo", "mistral-small", "command-r", "firefunction",
)

_CALL_PATTERN = re.compile(r'\{[\s\S]*"tool_call"[\s\S]*\}')


def supports_native_tools(model: str) -> bool:
    return any(hint in (model or "").lower() for hint in NATIVE_TOOL_MODELS)


def prompted_system(tools: list[Any]) -> str:
    """Describe the tool catalogue as a system-prompt instruction."""
    descriptions = [
        f"- {spec['name']}: {spec.get('description', '')} schema={json.dumps(spec.get('input_schema') or {})}"
        for spec in tool_specs(tools)
    ]
    return (
        "When you need to call a tool, respond with ONLY a JSON line of the form "
        '{"tool_call":{"name":"<tool>","arguments":{...}}}. '
        "Do not add prose. Tools available:\n" + "\n".join(descriptions)
    )


def parse_prompted_call(text: str) -> dict[str, Any] | None:
    """Recover a tool call from prose, or None when the reply carries none."""
    if not text:
        return None
    match = _CALL_PATTERN.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    call = payload.get("tool_call") or {}
    return {"id": f"call_{uuid.uuid4().hex[:8]}", "name": call.get("name", ""),
            "arguments": call.get("arguments") or {}}
