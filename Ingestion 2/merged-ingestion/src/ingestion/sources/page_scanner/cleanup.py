"""Optional, guarded OCR correction through the shared LLM gateway."""

from __future__ import annotations

import logging
import os
import unicodedata
from typing import Any, Protocol


log = logging.getLogger(__name__)

PROVIDER = os.getenv("HG_CLEANUP_PROVIDER", "gemma")
MODEL = os.getenv("HG_CLEANUP_MODEL") or None
DIFF_GUARD_FRAC = float(os.getenv("HG_CLEANUP_DIFF_GUARD", "0.15"))
CLEANUP_MAX_TOKENS = 2048

SYSTEM_PROMPT = (
    "You correct optical-character-recognition (OCR) errors in verbatim quotes "
    "extracted from highlighted book pages.\n"
    "Fix ONLY clear optical mistakes: l↔1, O↔0, rn↔m, cl↔d, broken hyphenation "
    "across a line break (e.g. 'under- stand' → 'understand'), and stray "
    "recognition artifacts.\n"
    "NEVER reword, paraphrase, translate, add, remove, reorder, summarise, or "
    "'improve' the text. Preserve the original wording, punctuation, casing, and "
    "British/American spelling exactly.\n"
    "If you are not confident a change is an OCR error, leave the text UNCHANGED.\n"
    "Return ONLY the corrected passage text with no preamble, no quotes, and no "
    "commentary."
)

class ChatClient(Protocol):
    def chat(
        self,
        prompt: str | None = None,
        *,
        system: Any = None,
        provider: str | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> dict[str, Any]: ...

def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    for source, replacement in [
        ("—", "-"),
        ("–", "-"),
        ("‑", "-"),
        ("’", "'"),
        ("‘", "'"),
        ("“", '"'),
        ("”", '"'),
    ]:
        value = value.replace(source, replacement)
    return " ".join(value.split()).strip()


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for index, left_character in enumerate(left, 1):
        current = [index]
        for right_index, right_character in enumerate(right, 1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1]
                    + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def _passes_diff_guard(raw: str, cleaned: str) -> bool:
    normalized_raw = _normalize(raw)
    normalized_cleaned = _normalize(cleaned)
    if not normalized_raw:
        return normalized_raw == normalized_cleaned
    return (
        _edit_distance(normalized_raw, normalized_cleaned) / len(normalized_raw)
        <= DIFF_GUARD_FRAC
    )


def _call_gateway(
    passage: str,
    *,
    chat_client: ChatClient | None = None,
    provider: str = PROVIDER,
) -> str:
    """Send one passage with no history; mandatory cleanup fails loudly."""

    if chat_client is None:
        raise RuntimeError(
            "cleanup requires a shared LLM gateway client"
        )
    try:
        response = chat_client.chat(
            passage,
            system=SYSTEM_PROMPT,
            provider=provider,
            model=MODEL,
            # Gemma may spend hundreds of output tokens on hidden reasoning
            # before emitting the corrected passage.  A character-derived
            # ceiling truncated a 715-character real passage at 779 tokens
            # with no visible text.  Keep the established client ceiling so
            # the verbatim output has room after reasoning.
            max_tokens=CLEANUP_MAX_TOKENS,
            temperature=0,
        )
        text = response.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(
                f"cleanup gateway returned no text (provider={provider})"
            )
        return text.strip()
    except Exception as error:
        raise RuntimeError(
            "cleanup gateway call failed "
            f"(provider={provider}, {type(error).__name__}: {error})"
        ) from error


def clean_passages(
    passages: list[str],
    *,
    chat_client: ChatClient | None = None,
    provider: str = PROVIDER,
) -> list[str]:
    """Correct each passage, preserving raw text only on diff-guard rejection."""

    output: list[str] = []
    cleaned_count = 0
    rejected_count = 0
    for raw in passages:
        if not raw or not raw.strip():
            output.append(raw)
            continue
        cleaned = _call_gateway(
            raw,
            chat_client=chat_client,
            provider=provider,
        )
        if cleaned == raw:
            output.append(raw)
        elif _passes_diff_guard(raw, cleaned):
            output.append(cleaned)
            cleaned_count += 1
        else:
            log.warning(
                "cleanup: rejected an over-large 'correction' (diff-guard, "
                ">%.0f%%); kept raw. raw=%r cleaned=%r",
                DIFF_GUARD_FRAC * 100,
                raw[:80],
                cleaned[:80],
            )
            output.append(raw)
            rejected_count += 1
    if cleaned_count or rejected_count:
        log.info(
            "cleanup: %d passage(s) corrected, %d rejected by diff-guard",
            cleaned_count,
            rejected_count,
        )
    return output
