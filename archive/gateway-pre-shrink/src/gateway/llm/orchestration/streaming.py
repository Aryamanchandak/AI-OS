"""SSE frame encoding for the streaming chat path.

Frame bytes are part of the contract (hard rule #2), so these helpers exist to
keep every frame's key set — and key *order*, which `json.dumps` preserves —
pinned to what `glc_v5/glc/routes/chat.py:826-933` emits. Tests assert against
these, not against the route.
"""

from __future__ import annotations

import json
from typing import Any

#: The longest an error string may be inside an SSE error frame.
ERROR_LIMIT = 300


def frame(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def delta_frame(provider: str, chunk: str) -> str:
    return frame({"provider": provider, "delta": chunk})


def tool_call_delta_frame(provider: str, payload: str) -> str:
    """The tool-call payload stays a JSON *string*, exactly as legacy sends it."""
    return frame({"provider": provider, "tool_call_delta": payload})


def error_frame(message: str) -> str:
    """Mid-stream errors carry no provider key — legacy's shape, deliberately."""
    return frame({"error": message[:ERROR_LIMIT]})


def done_frame(provider: str, model: str, profile: str | None, *, pin_unverified: bool = False) -> str:
    """Terminal frame. `profile_pin_unverified` appears only when a pinned
    profile was streamed by a provider that could not confirm its model
    mid-stream — the caller learns the pin went unchecked instead of being told
    it held."""
    payload: dict[str, Any] = {"done": True, "provider": provider, "model": model, "profile": profile}
    if pin_unverified:
        payload["profile_pin_unverified"] = True
    return frame(payload)
