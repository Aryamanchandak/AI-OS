# Agent guide: Compares raw and LLM-cleaned OCR against golden answers; unlike the regression check, this may call the LLM gateway.
"""One-off eval: does the LLM cleanup pass actually improve extraction?

This is DELIBERATELY separate from golden/check.py. That check is the
deterministic, offline, zero-cost regression gate and must stay that way — wiring
a non-deterministic paid LLM call into it would make it unrepeatable. This script
instead measures the *value-add* of --clean on the same golden pages:

  raw extraction  → edit distance to the human-confirmed answer   (baseline)
  cleaned         → edit distance to the same answer               (with --clean)

A drop in total edits = the cleanup helped; a rise = it hurt (investigate).

Requires the AI Code LLM gateway running on :8107 with a provider configured:
  cd "AI Code/llm_gateway" && .venv/bin/python main.py
  # + ANTHROPIC_API_KEY in AI Code/.env  (or:  export HG_CLEANUP_PROVIDER=openai-cheap)

  .venv/bin/python golden/eval_cleanup.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import cleanup                       # noqa: E402
from golden.check import extract_passages, levenshtein, normalize  # noqa: E402


def _best_edit(golden_text: str, candidates: list[str]) -> int:
    """Smallest normalized edit distance from a golden answer to any candidate."""
    g = normalize(golden_text)
    if not candidates:
        return len(g)
    return min(levenshtein(g, normalize(c)) for c in candidates)


def main() -> int:
    answers = json.loads((ROOT / "golden" / "answers.json").read_text())
    inbox = ROOT / "data" / "inbox"

    base_total = clean_total = n = 0
    print(f"Cleanup eval (provider={cleanup.PROVIDER}, gateway={cleanup.GATEWAY_URL})\n")
    for fname, golden_list in answers["pages"].items():
        img = inbox / fname
        if not img.exists():
            print(f"{fname}: MISSING — skipped")
            continue
        raw = extract_passages(img)
        cleaned = cleanup.clean_passages(raw)
        print(f"{fname}  ({len(golden_list)} golden / {len(raw)} extracted)")
        for gi, gtext in enumerate(golden_list, 1):
            b = _best_edit(gtext, raw)
            c = _best_edit(gtext, cleaned)
            n += 1
            base_total += b
            clean_total += c
            arrow = "→" if b == c else ("↓ better" if c < b else "↑ WORSE")
            print(f"  p{gi}: raw {b:>3} edits   clean {c:>3} edits   {arrow}")
        print()

    print("-" * 56)
    delta = clean_total - base_total
    verdict = "no change" if delta == 0 else ("IMPROVED" if delta < 0 else "REGRESSED")
    print(f"passages: {n}   total edits  raw={base_total}  clean={clean_total}   "
          f"({delta:+d} → {verdict})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
