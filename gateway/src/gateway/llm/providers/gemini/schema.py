"""Gemini's `responseSchema` dialect.

Gemini rejects `$ref`, so Pydantic-generated schemas — which emit refs for every
nested model — must be inlined before they are cleaned. Ported from
`_gemini_inline_refs` / `_gemini_clean_schema` in `glc_v5/glc/providers.py:958`.
"""

from __future__ import annotations

from typing import Any

#: Keys Gemini's responseSchema validator rejects outright.
DROPPED = {"additionalProperties", "$schema", "title", "definitions", "$defs", "examples", "default"}


def inline_refs(schema: Any) -> Any:
    """Resolve `$ref` pointers into `$defs` / `definitions` inline.

    Must run BEFORE `clean`, which strips `$defs` and would otherwise leave
    dangling pointers. Recursion is bounded by `seen`: a self-referential model
    resolves once and then drops the repeat, which Gemini would reject anyway.
    """
    if not isinstance(schema, dict):
        return schema
    defs = dict(schema.get("$defs") or schema.get("definitions") or {})

    def walk(node: Any, seen: frozenset[str] = frozenset()) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = str(node["$ref"])
                name = None
                if target.startswith("#/$defs/"):
                    name = target.removeprefix("#/$defs/")
                elif target.startswith("#/definitions/"):
                    name = target.removeprefix("#/definitions/")
                if name and name in defs and name not in seen:
                    resolved = walk(defs[name], seen | {name})
                    extras = {k: walk(v, seen) for k, v in node.items() if k != "$ref"}
                    return {**resolved, **extras} if isinstance(resolved, dict) else resolved
                # Unresolvable ref — drop it; Gemini would 400 on it regardless.
                return {k: walk(v, seen) for k, v in node.items() if k != "$ref"}
            return {k: walk(v, seen) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(item, seen) for item in node]
        return node

    return walk(schema)


def clean(schema: Any) -> Any:
    """Inline refs, then strip the JSON-Schema keys Gemini rejects."""
    schema = inline_refs(schema)
    if not isinstance(schema, dict):
        return schema

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k not in DROPPED}
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    return strip(schema)
