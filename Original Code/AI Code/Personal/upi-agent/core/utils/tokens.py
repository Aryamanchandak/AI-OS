"""Name tokenisation utilities shared across classifiers."""

from __future__ import annotations

import re

from core import config

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


def name_tokens(name: str | None) -> list[str]:
    """Lowercased meaningful tokens from a counterparty name."""
    if not name:
        return []
    out = []
    for tok in _TOKEN_RE.findall(name.lower()):
        if tok not in config.NAME_STOP_TOKENS:
            out.append(tok)
    return out
