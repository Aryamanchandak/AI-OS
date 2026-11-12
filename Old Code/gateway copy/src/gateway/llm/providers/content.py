"""Provider-agnostic content-block normalization.

These helpers translate the *neutral* request shape (system blocks, message
content lists, tool-call arguments) into the plain values each provider package
then dresses in its own dialect. Nothing here knows about a specific vendor —
the per-vendor translation lives in `providers/<name>/`.

Ported from `glc_v5/glc/providers.py` (`_flatten_system`, `_extract_text_blocks`,
`_iter_image_blocks`, `_coerce_obj`) and `glc_v5/glc/direct_providers.py`
(`_as_dict`, `_text`, `_arguments`), which are read-only sources.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
from typing import Any


def as_dict(value: Any) -> dict[str, Any] | None:
    """Coerce a Pydantic model or mapping to a plain dict, or None when empty."""
    if not value:
        return None
    if isinstance(value, dict):
        return value
    return dict(value.model_dump(by_alias=True))


def extract_text_blocks(content: Any) -> str:
    """Concatenate the text of every text block in a content list."""
    if not isinstance(content, list):
        return str(content or "")
    return "".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
    )


def text_of(value: Any) -> str:
    """Flatten any message content — string, block list, or object — to text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return extract_text_blocks(value)
    return json.dumps(value)


def iter_image_blocks(content: Any) -> Iterator[tuple[str, str]]:
    """Yield (media_type, base64_data) per image block.

    Assumes http(s) URLs were already resolved to `data:` form by the
    normalization stage, which is where SSRF policy is applied.
    """
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        url: Any = None
        if kind == "image_url":
            value = block.get("image_url")
            url = value.get("url") if isinstance(value, dict) else value
        elif kind in {"image", "input_image"}:
            source = block.get("source") or {}
            if isinstance(source, dict) and source.get("type") == "base64":
                yield source.get("media_type", "image/png"), source.get("data", "")
                continue
            url = block.get("url") or (source.get("url") if isinstance(source, dict) else None)
        if not isinstance(url, str) or not url.startswith("data:"):
            continue
        head, _, data = url.partition(",")
        yield head[5:].split(";")[0] or "image/png", data


def content_has_image(content: Any) -> bool:
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") in {"image_url", "image", "input_image"}
        for block in content
    )


def flatten_system(system: Any) -> tuple[str, list[dict[str, Any]], bool]:
    """Return (joined_text, raw_blocks, has_cache_marker).

    `has_cache_marker` is what turns on per-block prompt caching for the
    providers that support it; a bare string carries no marker.
    """
    if system is None:
        return "", [], False
    if isinstance(system, str):
        return system, [{"text": system, "cache": False}], False
    blocks: list[dict[str, Any]] = []
    parts: list[str] = []
    has_cache = False
    for block in system:
        if isinstance(block, dict):
            value, cache = block.get("text", ""), bool(block.get("cache", False))
        else:
            value, cache = getattr(block, "text", ""), bool(getattr(block, "cache", False))
        blocks.append({"text": value, "cache": cache})
        parts.append(value)
        has_cache = has_cache or cache
    return "\n".join(parts), blocks, has_cache


def coerce_obj(value: Any) -> Any:
    """Coerce a tool result into the object shape Gemini's functionResponse wants."""
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"text": value}
    return {"value": value}


def arguments(value: Any) -> dict[str, Any]:
    """Normalize a tool call's arguments to a dict, however the vendor sent them."""
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {"_raw": str(value)}
    return parsed if isinstance(parsed, dict) else {"_value": parsed}


def tool_specs(tools: list[Any] | None) -> list[dict[str, Any]]:
    """Normalize the declared tools to plain dicts, preserving order."""
    if not tools:
        return []
    return [tool if isinstance(tool, dict) else tool.model_dump() for tool in tools]
