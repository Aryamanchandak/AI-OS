from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass


log = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("LLM_GATEWAY_V7_URL", "http://localhost:8107").rstrip("/")
PROVIDER = os.getenv("HG_SPELLCHECK_PROVIDER", "anthropic-haiku")
MODEL = os.getenv("HG_SPELLCHECK_MODEL") or None
TIMEOUT = float(os.getenv("HG_SPELLCHECK_TIMEOUT", "60"))
MAX_EDIT_DISTANCE = int(os.getenv("HG_SPELLCHECK_MAX_EDIT_DISTANCE", "3"))

SYSTEM_PROMPT = (
    "You propose spelling fixes for a mutable markdown note after glossary "
    "abbreviation expansion has already run.\n"
    'Return ONLY a JSON object shaped as {"edits":[...]}. Each edits item must '
    'be an object with exactly these keys: "line", "original", "suggested".\n'
    "Rules:\n"
    "- Suggest ONLY real dictionary-word spelling errors you are certain about.\n"
    "- NEVER expand abbreviations, acronyms, symbols, or shorthand.\n"
    "- NEVER reword, rewrite, improve grammar, change punctuation, change casing "
    "unless casing is part of the misspelling, or alter style.\n"
    "- NEVER suggest proper-name, title, code, URL, path, or markdown syntax changes.\n"
    "- Use 1-based line numbers from the provided text.\n"
    "- The original value must be the exact misspelled text as it appears on that line.\n"
    '- If there are no certain spelling errors, return {"edits":[]}.'
)

_warned: set[str] = set()


@dataclass(frozen=True)
class Edit:
    line: int
    original: str
    suggested: str

    def to_dict(self) -> dict:
        return asdict(self)


def propose_spelling_fixes(text: str) -> list[dict]:
    if not text.strip():
        return []

    payload = _call_gateway(text)
    if payload is None:
        return []

    edits = _parse_edits(payload)
    return [edit.to_dict() for edit in _guard_edits(text, edits)]


def _call_gateway(text: str) -> str | None:
    body = {
        "prompt": _user_prompt(text),
        "system": SYSTEM_PROMPT,
        "provider": PROVIDER,
        "max_tokens": 1200,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    if MODEL:
        body["model"] = MODEL

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{GATEWAY_URL}/v1/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("text")
        if not isinstance(result, str):
            _warn_once("empty", "spellcheck: gateway returned no text; no suggestions")
            return None
        return result.strip()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        _warn_once(
            f"http{e.code}",
            f"spellcheck: gateway rejected call (HTTP {e.code}, provider={PROVIDER}); "
            f"no suggestions. Detail: {detail}",
        )
        return None
    except urllib.error.URLError as e:
        _warn_once(
            "unreachable",
            f"spellcheck: LLM gateway unreachable at {GATEWAY_URL} ({e.reason}); no suggestions",
        )
        return None
    except Exception as e:
        _warn_once(
            "other",
            f"spellcheck: unexpected gateway error ({type(e).__name__}: {e}); no suggestions",
        )
        return None


def _user_prompt(text: str) -> str:
    numbered = "\n".join(
        f"{index}: {line}" for index, line in enumerate(text.splitlines(), start=1)
    )
    return (
        "Find only certain dictionary-word spelling errors in this numbered text. "
        'Return JSON only, shaped as {"edits":[...]}. \n\n'
        f"{numbered}"
    )


def _parse_edits(payload: str) -> list[Edit]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", payload)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

    if isinstance(data, dict):
        data = data.get("edits") or data.get("suggestions") or []
    if not isinstance(data, list):
        return []

    edits: list[Edit] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            line = int(item.get("line"))
        except (TypeError, ValueError):
            continue
        original = str(item.get("original") or "").strip()
        suggested = str(item.get("suggested") or "").strip()
        if not original or not suggested or original == suggested:
            continue
        edits.append(Edit(line=line, original=original, suggested=suggested))
    return edits


def _guard_edits(text: str, edits: list[Edit]) -> list[Edit]:
    lines = text.splitlines()
    accepted: list[Edit] = []
    seen: set[tuple[int, str, str]] = set()

    for edit in edits:
        key = (edit.line, edit.original, edit.suggested)
        if key in seen:
            continue
        seen.add(key)
        if edit.line < 1 or edit.line > len(lines):
            continue
        if edit.original not in lines[edit.line - 1]:
            continue
        if not _single_tokenish(edit.original) or not _single_tokenish(edit.suggested):
            continue
        if edit.original.lower() == edit.suggested.lower():
            continue
        if _looks_like_abbreviation(edit.original):
            continue
        if _edit_distance(_normalize(edit.original), _normalize(edit.suggested)) > MAX_EDIT_DISTANCE:
            log.info("spellcheck: dropped over-large edit %r -> %r", edit.original, edit.suggested)
            continue
        accepted.append(edit)
    return accepted


def _single_tokenish(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z'’-]*", value))


def _looks_like_abbreviation(value: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", value)
    return len(letters) <= 2 or letters.isupper()


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    for left, right in [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-")]:
        value = value.replace(left, right)
    return value.strip()


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _warn_once(key: str, message: str) -> None:
    if key in _warned:
        return
    _warned.add(key)
    log.warning(message)
