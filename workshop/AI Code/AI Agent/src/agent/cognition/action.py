"""Action: MCP dispatcher.

Pure dispatch — no LLM here. When a tool result is large, this layer pushes
the bytes to the artifact store and returns the handle alongside a short
descriptor. Memory will record both. Decision never sees the bytes unless
Perception decides a later goal needs them.
"""

from __future__ import annotations

import json
from typing import Any

from mcp import ClientSession

from agent.services import artifacts
from agent.schemas import ToolCall

# Tool outputs larger than this go to the artifact store rather than into
# memory/decision context. 4 KB is roughly one A4 page of text.
ARTIFACT_THRESHOLD_BYTES = 4096


def _content_type_for_part(part: Any) -> str:
    if getattr(part, "text", None) is not None:
        return "text/plain"
    mime = (
        getattr(part, "mimeType", None)
        or getattr(part, "mime_type", None)
        or getattr(getattr(part, "resource", None), "mimeType", None)
        or getattr(getattr(part, "resource", None), "mime_type", None)
    )
    if isinstance(mime, str) and mime.strip():
        return mime
    return "application/octet-stream"


def _result_to_text_and_content_type(result: Any) -> tuple[str, str]:
    """Collapse an MCP CallToolResult into text plus best-effort content type."""
    if not getattr(result, "content", None):
        return "", "text/plain"
    parts: list[str] = []
    content_types: list[str] = []
    for c in result.content:
        content_types.append(_content_type_for_part(c))
        text = getattr(c, "text", None)
        if text is not None:
            parts.append(text)
        else:
            # TODO: non-text content types need a bytes-preserving artifact path.
            parts.append(str(c))
    unique_types = set(content_types)
    if len(unique_types) == 1:
        content_type = content_types[0]
    elif unique_types <= {"text/plain"}:
        content_type = "text/plain"
    else:
        content_type = "multipart/mixed"
    return "\n".join(parts), content_type


def _result_to_text(result: Any) -> str:
    """Collapse an MCP CallToolResult into one text string."""
    return _result_to_text_and_content_type(result)[0]


async def execute(
    session: ClientSession,
    tool_call: ToolCall,
) -> tuple[str, str | None]:
    """Run one MCP tool call. Returns (descriptor, artifact_id_or_None).

    When the result is larger than ARTIFACT_THRESHOLD_BYTES, the full bytes
    are written to the artifact store and the returned descriptor is a short
    preview plus the artifact id.
    """
    # Decision sometimes hallucinates that `art:...` handles are file paths
    # or URLs. Block that here so the bad call doesn't waste an iteration.
    for arg_name in ("path", "url"):
        v = tool_call.arguments.get(arg_name)
        if isinstance(v, str) and v.startswith("art:"):
            return (
                f"ERROR: {arg_name}={v!r} is an artifact handle, not a "
                f"path/URL. Artifact bytes are attached by Perception when "
                f"needed — answer from ATTACHED ARTIFACTS instead of calling "
                f"{tool_call.name}.",
                None,
            )

    result = await session.call_tool(tool_call.name, arguments=tool_call.arguments)
    text, content_type = _result_to_text_and_content_type(result)
    nbytes = len(text.encode("utf-8"))

    if nbytes > ARTIFACT_THRESHOLD_BYTES:
        art_id = artifacts.put(
            text.encode("utf-8"),
            content_type=content_type,
            source=f"mcp:{tool_call.name}",
            descriptor=f"{tool_call.name}({json.dumps(tool_call.arguments)[:80]}) → {nbytes} bytes",
        )
        descriptor = (
            f"[artifact {art_id}, {nbytes} bytes] preview: "
            + text[:240].replace("\n", " ")
            + ("..." if nbytes > 240 else "")
        )
        return descriptor, art_id

    return text, None
