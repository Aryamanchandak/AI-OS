# Agent guide: Optional guarded LLM cleanup for OCR text; preserves raw OCR and falls back safely on errors or large rewrites.
"""Optional Claude text-cleanup pass (OCR follow-up #2).

After OCR, each highlighted passage's *text* (never the image) is sent through a
conservative LLM call that fixes obvious optical mistakes (l↔1, O↔0, rn↔m, broken
line-break hyphenation, stray artifacts) and pre-fills the cockpit's editable
`edited_text`. The raw recognizer output always stays in `ocr_text`, so nothing
is lost and the human review gate is still the backstop.

Safety is layered — every one of these holds even if the model misbehaves:
  1. A conservative system prompt that forbids rewording/adding/removing text.
  2. temperature = 0 (deterministic, no creative drift).
  3. A diff-guard: if the *normalized* edit distance between raw and cleaned
     exceeds DIFF_GUARD_FRAC of the length, the correction is rejected and the
     raw OCR is kept — a large silent rewrite can never slip through.
  4. Raw OCR preserved in `ocr_text`; cleanup only ever pre-fills `edited_text`.
  5. The cockpit human-accept gate downstream.

The LLM call is routed through the shared **LLM gateway** in `AI Code/` (a local
FastAPI service on :8107), not the raw `anthropic` SDK — so this project needs no
API key of its own and no new dependency (stdlib `urllib` only). The gateway must
be running and have the chosen provider configured; if it is unreachable or the
provider is unavailable, cleanup **degrades gracefully to the raw OCR** and logs a
loud, actionable warning (it never crashes the batch).

Setup for `--clean` to actually do anything:
  • Start the gateway:  cd "AI Code/llm_gateway" && ./run.sh   (port 8107)
  • Give it an Anthropic key:  add ANTHROPIC_API_KEY=... to AI Code/.env
    (the default provider is `anthropic-haiku` → claude-haiku-4-5).
  • Or point at a provider you already have configured, e.g.:
      export HG_CLEANUP_PROVIDER=openai-cheap
"""

from __future__ import annotations

import json
import logging
import os
import unicodedata
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

# ── Config (all overridable via env; sensible defaults) ──────────────────────
GATEWAY_URL = os.getenv("LLM_GATEWAY_V7_URL", "http://localhost:8107").rstrip("/")
# The plan's intended tier: haiku is the right model for constrained correction
# ("you do NOT need Opus/Sonnet to fix rn→m"). Override to any provider the
# gateway has configured, e.g. HG_CLEANUP_PROVIDER=openai-cheap.
PROVIDER = os.getenv("HG_CLEANUP_PROVIDER", "anthropic-haiku")
MODEL = os.getenv("HG_CLEANUP_MODEL") or None      # None → gateway's default for the provider
TIMEOUT = float(os.getenv("HG_CLEANUP_TIMEOUT", "60"))

# Diff-guard: reject any "correction" that changes more than this fraction of the
# (normalized) passage. Starts at 15% per the plan — a genuine OCR fix is a few
# characters; anything larger is a reword and is thrown away in favour of raw OCR.
DIFF_GUARD_FRAC = float(os.getenv("HG_CLEANUP_DIFF_GUARD", "0.15"))

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

# Warn at most once per distinct reason per process, so a down gateway logs a
# single actionable line instead of one per passage.
_warned: set[str] = set()


def _warn_once(key: str, msg: str) -> None:
    if key not in _warned:
        _warned.add(key)
        log.warning(msg)


def _normalize(s: str) -> str:
    """Fold cosmetic differences that are NOT OCR errors (curly↔straight quotes,
    dashes, whitespace) so the diff-guard measures real character changes only.
    Mirrors golden/check.py::normalize; case is preserved."""
    s = unicodedata.normalize("NFKC", s)
    for a, b in [("—", "-"), ("–", "-"), ("‑", "-"),
                 ("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')]:
        s = s.replace(a, b)
    return " ".join(s.split()).strip()


def _edit_distance(a: str, b: str) -> int:
    """Classic Levenshtein DP (insert/delete/substitute = 1)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _passes_diff_guard(raw: str, cleaned: str) -> bool:
    """True if `cleaned` is a small enough edit of `raw` to trust as an OCR fix."""
    rn, cn = _normalize(raw), _normalize(cleaned)
    if not rn:
        return rn == cn
    frac = _edit_distance(rn, cn) / len(rn)
    return frac <= DIFF_GUARD_FRAC


def _call_gateway(passage: str) -> str | None:
    """Send one passage to the gateway → corrected text, or None on any problem.

    None means "keep the raw OCR" — the caller degrades gracefully. A None is
    logged (once per reason) so a misconfigured/unreachable gateway is visible.
    """
    body = {
        "prompt": passage,
        "system": SYSTEM_PROMPT,
        "provider": PROVIDER,
        "max_tokens": max(64, min(len(passage) + 64, 1024)),
        "temperature": 0,          # deterministic; part of the safety story
    }
    if MODEL:
        body["model"] = MODEL
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{GATEWAY_URL}/v1/chat", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            _warn_once("empty", f"cleanup: gateway returned no text (provider={PROVIDER}); keeping raw OCR")
            return None
        return text.strip()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        # Most likely cause: the chosen provider isn't configured on the gateway
        # (e.g. no ANTHROPIC_API_KEY in AI Code/.env for provider=anthropic-haiku).
        _warn_once(
            f"http{e.code}",
            f"cleanup: gateway rejected the call (HTTP {e.code}, provider={PROVIDER}). "
            f"Cleanup is DISABLED for this run — raw OCR kept. "
            f"Check the provider is configured (add ANTHROPIC_API_KEY to AI Code/.env, "
            f"or set HG_CLEANUP_PROVIDER to a configured provider). Detail: {detail}",
        )
        return None
    except urllib.error.URLError as e:
        _warn_once(
            "unreachable",
            f"cleanup: LLM gateway unreachable at {GATEWAY_URL} ({e.reason}). "
            f"Cleanup is DISABLED for this run — raw OCR kept. "
            f"Start it: cd 'AI Code/llm_gateway' && ./run.sh (port 8107).",
        )
        return None
    except Exception as e:                                   # never kill the batch
        _warn_once("other", f"cleanup: unexpected error calling gateway ({type(e).__name__}: {e}); keeping raw OCR")
        return None


def clean_passages(passages: list[str]) -> list[str]:
    """Correct OCR errors in each passage via the LLM gateway.

    Returns a list the SAME length as the input; each element is either the
    corrected text or — when the model is unavailable, returns nothing, or the
    diff-guard rejects an over-large edit — the **unchanged raw passage**. Never
    drops, reorders, or raises. Empty/whitespace passages are passed through.
    """
    out: list[str] = []
    n_cleaned = n_rejected = 0
    for raw in passages:
        if not raw or not raw.strip():
            out.append(raw)
            continue
        cleaned = _call_gateway(raw)
        if cleaned is None:
            out.append(raw)
            continue
        if cleaned == raw:
            out.append(raw)
            continue
        if _passes_diff_guard(raw, cleaned):
            out.append(cleaned)
            n_cleaned += 1
        else:
            # Too large to be an OCR fix — reject, keep raw, make it visible.
            log.warning(
                "cleanup: rejected an over-large 'correction' (diff-guard, "
                ">%.0f%%); kept raw. raw=%r cleaned=%r",
                DIFF_GUARD_FRAC * 100, raw[:80], cleaned[:80],
            )
            out.append(raw)
            n_rejected += 1
    if n_cleaned or n_rejected:
        log.info("cleanup: %d passage(s) corrected, %d rejected by diff-guard",
                 n_cleaned, n_rejected)
    return out
