"""Dated, versioned pricing table for all Anthropic models.

Add a new PricingEntry when rates change; historical runs cost at price-at-time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class ModelPricing:
    input_per_million: float   # USD per 1M input tokens
    output_per_million: float  # USD per 1M output tokens


@dataclass
class PricingEntry:
    effective_date: date
    prices: dict[str, ModelPricing] = field(default_factory=dict)


_PRICING_TABLE: list[PricingEntry] = [
    PricingEntry(
        effective_date=date(2024, 1, 1),
        prices={
            "claude-3-opus-20240229": ModelPricing(input_per_million=15.0, output_per_million=75.0),
            "claude-3-sonnet-20240229": ModelPricing(input_per_million=3.0, output_per_million=15.0),
            "claude-3-haiku-20240307": ModelPricing(input_per_million=0.25, output_per_million=1.25),
        },
    ),
    PricingEntry(
        effective_date=date(2025, 1, 1),
        prices={
            "claude-opus-4-7": ModelPricing(input_per_million=15.0, output_per_million=75.0),
            "claude-sonnet-4-6": ModelPricing(input_per_million=3.0, output_per_million=15.0),
            "claude-haiku-4-5-20251001": ModelPricing(input_per_million=0.8, output_per_million=4.0),
        },
    ),
]


def get_price_at(model: str, when: date) -> ModelPricing:
    """Return the pricing active for `model` on `when`. Falls back to Sonnet tier."""
    active: ModelPricing | None = None
    for entry in _PRICING_TABLE:
        if entry.effective_date <= when and model in entry.prices:
            active = entry.prices[model]
    return active or ModelPricing(input_per_million=3.0, output_per_million=15.0)


def compute_cost(model: str, tokens_in: int, tokens_out: int, when: date | None = None) -> float:
    pricing = get_price_at(model, when or date.today())
    return (tokens_in * pricing.input_per_million + tokens_out * pricing.output_per_million) / 1_000_000
