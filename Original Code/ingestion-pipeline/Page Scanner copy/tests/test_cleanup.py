# Agent guide: Offline tests for cleanup correctness, diff-guard behavior, fallback safety, and passage-order invariants.
"""Cleanup-pass safety proofs (OCR follow-up #2) — all offline.

These never touch the network: the gateway call is stubbed, so they prove the
*guardrails* around whatever the model returns:
  • real OCR garbles get applied,
  • a clean quote is returned byte-for-byte,
  • a large rewrite is rejected by the diff-guard (raw kept),
  • an unavailable gateway degrades gracefully to raw (never raises),
  • cosmetic curly-quote/dash differences don't burn the diff-guard budget.

  .venv/bin/python tests/test_cleanup.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import cleanup  # noqa: E402


def _stub(mapping):
    """Return a _call_gateway replacement that maps raw→cleaned (or None)."""
    def fake(passage: str):
        return mapping.get(passage, passage)   # default: echo unchanged
    return fake


def test_real_garble_is_applied(monkeypatch) -> None:
    raw = "The systern was broken"
    monkeypatch.setattr(cleanup, "_call_gateway", _stub({raw: "The system was broken"}))
    assert cleanup.clean_passages([raw]) == ["The system was broken"]
    print("  garble applied: 'systern' → 'system'  ✓")


def test_clean_quote_returned_verbatim(monkeypatch) -> None:
    raw = "You do not rise to the level of your goals."
    monkeypatch.setattr(cleanup, "_call_gateway", _stub({raw: raw}))
    assert cleanup.clean_passages([raw]) == [raw]
    print("  clean quote: returned byte-for-byte  ✓")


def test_diff_guard_rejects_large_rewrite(monkeypatch) -> None:
    raw = "Habits are the compound interest of self-improvement."
    reworded = "Small routines accumulate into major long-term personal growth over time."
    monkeypatch.setattr(cleanup, "_call_gateway", _stub({raw: reworded}))
    # Over-large edit → rejected → raw kept (a reword can never slip through).
    assert cleanup.clean_passages([raw]) == [raw]
    print("  diff-guard: over-large rewrite rejected, raw kept  ✓")


def test_gateway_unavailable_degrades_to_raw(monkeypatch) -> None:
    raw = "anything at all"
    monkeypatch.setattr(cleanup, "_call_gateway", lambda p: None)   # gateway down
    assert cleanup.clean_passages([raw]) == [raw]
    print("  gateway down: degrades to raw, no crash  ✓")


def test_cosmetic_diffs_do_not_burn_budget(monkeypatch) -> None:
    """Curly→straight quote + em-dash normalisation is not counted as an edit,
    so a genuinely tiny fix under those cosmetics still passes the guard."""
    raw = 'He said “go—now”, l think'          # curly quotes, em-dash, l-for-I
    cleaned = 'He said "go-now", I think'                     # only the l→I is a real change
    monkeypatch.setattr(cleanup, "_call_gateway", _stub({raw: cleaned}))
    assert cleanup.clean_passages([raw]) == [cleaned]
    print("  cosmetics folded: tiny real fix still applied under quote/dash noise  ✓")


def test_length_and_order_preserved(monkeypatch) -> None:
    passages = ["one", "", "  ", "three"]
    monkeypatch.setattr(cleanup, "_call_gateway", _stub({"one": "one", "three": "three"}))
    out = cleanup.clean_passages(passages)
    assert len(out) == len(passages) and out[1] == "" and out[2] == "  "
    print("  invariants: same length/order, blanks passed through  ✓")


def _run_all() -> None:
    """Minimal monkeypatch shim so this runs as a plain script (no pytest needed)."""
    class MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def restore(self):
            for obj, name, val in reversed(self._undo):
                setattr(obj, name, val)
            self._undo.clear()

    tests = [
        test_real_garble_is_applied, test_clean_quote_returned_verbatim,
        test_diff_guard_rejects_large_rewrite, test_gateway_unavailable_degrades_to_raw,
        test_cosmetic_diffs_do_not_burn_budget, test_length_and_order_preserved,
    ]
    print("Cleanup-pass safety proofs:")
    for t in tests:
        mp = MP()
        try:
            t(mp)
        finally:
            mp.restore()
    print("\nall passed ✓")


if __name__ == "__main__":
    _run_all()
