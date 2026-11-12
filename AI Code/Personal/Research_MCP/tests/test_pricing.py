"""Unit tests for the pricing table."""
from datetime import date
from research_mcp.pricing import compute_cost, get_price_at


def test_known_model_price():
    p = get_price_at("claude-sonnet-4-6", date(2025, 6, 1))
    assert p.input_per_million == 3.0
    assert p.output_per_million == 15.0


def test_opus_price():
    p = get_price_at("claude-opus-4-7", date(2025, 6, 1))
    assert p.input_per_million == 15.0


def test_unknown_model_fallback():
    p = get_price_at("some-unknown-model", date(2025, 6, 1))
    assert p.input_per_million == 3.0  # Sonnet fallback


def test_cost_calculation():
    cost = compute_cost("claude-sonnet-4-6", tokens_in=1_000_000, tokens_out=0, when=date(2025, 6, 1))
    assert abs(cost - 3.0) < 0.001


def test_zero_tokens_is_zero_cost():
    assert compute_cost("claude-sonnet-4-6", 0, 0) == 0.0
