from __future__ import annotations

import json
from typing import Any

from .models import CompletionRequest, CompletionResponse


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Transcript contains a non-JSON value: {type(value).__name__}")


def serialize_transcript(
    request: CompletionRequest,
    partial_response: CompletionResponse | None = None,
) -> str:
    """Render every executor-visible input and partial output without summarizing it."""
    transcript: dict[str, Any] = {
        "system": request.system,
        "tools": _plain(request.tools),
        "messages": _plain(request.messages),
    }
    if partial_response is not None:
        transcript["partial_current_turn"] = {
            "role": "assistant",
            "content": _plain(partial_response.content),
            "stop_reason": partial_response.stop_reason,
        }
    encoded = json.dumps(
        transcript,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    byte_length = len(encoded.encode("utf-8"))
    return (
        f'BEGIN_QUOTED_EXECUTOR_TRANSCRIPT bytes="{byte_length}" format="canonical-json"\n'
        f"{encoded}\n"
        "END_QUOTED_EXECUTOR_TRANSCRIPT"
    )
