"""Deterministic identity helpers.

Normalization is deliberately lexical.  It creates resolver candidates; it
does not make a semantic identity decision.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_label(value: str) -> str:
    """Normalize Unicode, case, whitespace, and punctuation for lookup."""

    value = unicodedata.normalize("NFKC", value).casefold().strip()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def external_id_key(namespace: str, value: str) -> str:
    """Return a stable, unambiguous lookup key for an external identifier."""

    namespace = normalize_label(namespace).replace(" ", "_")
    normalized_value = unicodedata.normalize("NFKC", value).strip().casefold()
    if not namespace or not normalized_value:
        raise ValueError("external identifier namespace and value are required")
    return f"{namespace}:{normalized_value}"
