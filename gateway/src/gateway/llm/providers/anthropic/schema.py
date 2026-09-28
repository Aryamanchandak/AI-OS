"""Anthropic's structured-output schema dialect.

Anthropic's constrained decoder rejects the numeric and string constraint
keywords JSON Schema allows. Dropping them silently would loosen the contract,
so each one is restated as prose in the node's `description` — the model still
sees the requirement, and final validation runs against the *original* schema in
the structured-output stage. Ported from `anthropic_clean_schema` in
`glc_v5/glc/direct_providers.py:58`.
"""

from __future__ import annotations

from typing import Any

CONSTRAINTS = {
    "minimum": "Must be greater than or equal to {value}.",
    "maximum": "Must be less than or equal to {value}.",
    "exclusiveMinimum": "Must be greater than {value}.",
    "exclusiveMaximum": "Must be less than {value}.",
    "multipleOf": "Must be a multiple of {value}.",
    "minLength": "String length must be at least {value}.",
    "maxLength": "String length must be at most {value}.",
    "minItems": "Array must contain at least {value} item(s).",
    "maxItems": "Array must contain at most {value} item(s).",
    "minProperties": "Object must contain at least {value} properties.",
    "maxProperties": "Object must contain at most {value} properties.",
}
DROPPED = {"$schema", "default", "deprecated", "examples", "readOnly", "writeOnly"}


def clean(schema: Any) -> Any:
    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        result: dict[str, Any] = {}
        notes: list[str] = []
        for key, value in node.items():
            if key in CONSTRAINTS:
                notes.append(CONSTRAINTS[key].format(value=value))
            elif key in DROPPED:
                continue
            elif key == "format":
                notes.append(f"Expected string format: {value}.")
            else:
                result[key] = walk(value)
        if result.get("type") == "object" or "properties" in result:
            result["additionalProperties"] = False
        if notes:
            result["description"] = f"{result.get('description', '')} {' '.join(notes)}".strip()
        return result

    return walk(schema)
