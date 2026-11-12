"""Phase 3 — guards in isolation (§3.7)."""

from react_loop.guards import RepeatGuard, truncate_observation


def test_truncation_caps_length():
    out = truncate_observation("x" * 100, 10)
    assert out.startswith("x" * 10)
    assert "truncated" in out
    assert len(out) < 100 + 80  # cap + short suffix


def test_truncation_passes_short_text():
    assert truncate_observation("short", 100) == "short"


def test_repeat_guard_detects_consecutive_identical():
    g = RepeatGuard()
    assert g.is_repeat("get_time", {}) is False
    assert g.is_repeat("get_time", {}) is True  # same again -> repeat


def test_repeat_guard_arg_order_independent():
    g = RepeatGuard()
    g.is_repeat("t", {"a": 1, "b": 2})
    assert g.is_repeat("t", {"b": 2, "a": 1}) is True


def test_repeat_guard_resets_on_change():
    g = RepeatGuard()
    g.is_repeat("get_time", {})
    assert g.is_repeat("currency_convert", {"amount": 1}) is False
