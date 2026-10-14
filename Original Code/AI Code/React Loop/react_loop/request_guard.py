"""Small request-level guards that run before tool planning."""

from __future__ import annotations

import re

_FILE_REF_RE = re.compile(r"\b[\w .-]+\.[A-Za-z0-9]{1,8}\b")
_VAGUE_PATTERNS = (
    re.compile(r"^\s*(can you\s+)?(make|improve|fix|clean up|polish|rewrite)\s+(this|it|the above)\s*(better)?[?.!]?\s*$", re.I),
    re.compile(r"^\s*(turn|convert)\s+(this|it|the above)\s+into\s+.+[?.!]?\s*$", re.I),
)

_MISSING_TARGET_RESPONSE = (
    "Please paste the content or identify the file you would like me to improve."
)


def unresolved_reference_response(task: str) -> str | None:
    """Return a clarification response when the task lacks a concrete target.

    This intentionally only handles high-confidence cases. Contextual references
    with pasted content, named files, or longer instructions continue through the
    normal loop.
    """
    text = task.strip()
    if not text:
        return None
    if "\n" in text or ":" in text or _FILE_REF_RE.search(text):
        return None
    if any(pattern.match(text) for pattern in _VAGUE_PATTERNS):
        return _MISSING_TARGET_RESPONSE
    return None
