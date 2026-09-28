"""Content-free diagnostics and redacted provider errors."""
from __future__ import annotations

import os
import re


def safe_error(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    for key, secret in os.environ.items():
        if len(secret) >= 8 and any(word in key.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "API_KEY")):
            text = text.replace(secret, "[redacted]")
    for pattern in (
        r"(?i)bearer\s+[^\s,;]+",
        r"(?i)(authorization|x-api-key|api[_ -]?key)\s*[:=]\s*(?:[A-Za-z]+\s+)?[^\s,;]+",
        r"\bsk-[A-Za-z0-9_-]{8,}\b",
    ):
        text = re.sub(pattern, "[redacted]", text)
    return text[:300]
