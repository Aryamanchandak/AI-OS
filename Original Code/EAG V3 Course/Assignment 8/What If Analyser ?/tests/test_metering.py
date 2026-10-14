"""Offline checks for per-run Gemini usage and INR estimates."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.metering import (
    MeteredGeminiClient,
    ModelCallLimitExceeded,
    UsageLedger,
)


class _FakeModels:
    def generate_content(self, **kwargs):
        return SimpleNamespace(
            usage_metadata=SimpleNamespace(
                prompt_token_count=1_000,
                cached_content_token_count=200,
                candidates_token_count=100,
                thoughts_token_count=50,
            )
        )


def test_usage_is_costed_from_returned_metadata() -> None:
    updates = []
    ledger = UsageLedger(on_update=updates.append, max_calls=3, usd_to_inr=95)
    client = MeteredGeminiClient(
        ledger,
        inner=SimpleNamespace(models=_FakeModels()),
    )

    client.models.generate_content(model="gemini-3.1-pro-preview", contents="test")
    usage = ledger.snapshot()

    assert usage["calls"] == 1
    assert usage["completed_calls"] == 1
    assert usage["input_tokens"] == 1_000
    assert usage["output_tokens"] == 100
    assert usage["thinking_tokens"] == 50
    assert usage["cost_usd"] == 0.00344
    assert usage["cost_inr"] == 0.33
    assert updates[-1] == usage


def test_call_guard_is_not_a_rupee_spending_ceiling() -> None:
    ledger = UsageLedger(max_calls=1, usd_to_inr=95)
    client = MeteredGeminiClient(
        ledger,
        inner=SimpleNamespace(models=_FakeModels()),
    )

    client.models.generate_content(model="gemini-3.1-pro-preview", contents="first")
    try:
        client.models.generate_content(model="gemini-3.1-pro-preview", contents="second")
    except ModelCallLimitExceeded:
        pass
    else:
        raise AssertionError("expected the technical call guard to stop call two")


if __name__ == "__main__":
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_")
    ]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")
