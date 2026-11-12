"""Per-model pricing loaded from operator configuration."""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    cache_read_multiplier: float = 1.0
    cache_write_multiplier: float = 1.0
    batch_multiplier: float = 1.0
    quality: float = 0.5
    source: str = "unpriced_default"

    @property
    def priced(self) -> bool:
        return self.source != "unpriced_default"


class PricingTable:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw

    @classmethod
    def from_yaml(cls, path: Path) -> "PricingTable":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if raw.get("version") != 1: raise ValueError(f"{path}: version must be 1")
        return cls(raw)

    def price_for(self, provider: str, model: str | None) -> ModelPrice:
        defaults = self.raw.get("defaults") or {}
        name = model or ""
        spec = (self.raw.get("models") or {}).get(name)
        source = f"models.{name}"
        if spec is None and "/" in name:
            spec = (self.raw.get("models") or {}).get(name.split("/", 1)[1]); source = f"models.{name.split('/', 1)[1]}"
        if spec is None:
            for row in self.raw.get("patterns") or []:
                if fnmatch.fnmatch(name, row.get("match", "")): spec, source = row, f"patterns.{row.get('match')}"; break
        if spec is None:
            base = provider.split("_", 1)[0].split("-", 1)[0]
            spec = (self.raw.get("providers") or {}).get(base); source = f"providers.{base}"
        if spec is None:
            spec = self.raw.get("unpriced_default") or {}; source = "unpriced_default"
        return ModelPrice(float(spec.get("input", 0)), float(spec.get("output", 0)),
            float(spec.get("cache_read_multiplier", defaults.get("cache_read_multiplier", 1))),
            float(spec.get("cache_write_multiplier", defaults.get("cache_write_multiplier", 1))),
            float(spec.get("batch_multiplier", defaults.get("batch_multiplier", 1))), float(spec.get("quality", .5)), source)

    def project(self, provider: str, model: str | None, input_tokens: int, output_tokens: int, *, batch: bool = False) -> float:
        price = self.price_for(provider, model); multiplier = price.batch_multiplier if batch else 1.0
        return multiplier * (input_tokens * price.input_usd_per_mtok + output_tokens * price.output_usd_per_mtok) / 1_000_000

    def cost(self, provider: str, model: str | None, usage: Any, *, batch: bool = False) -> dict[str, Any]:
        price = self.price_for(provider, model); multiplier = price.batch_multiplier if batch else 1.0
        normal_input = max(0, usage.input_tokens - usage.cache_read_input_tokens - usage.cache_creation_input_tokens)
        total = multiplier * (normal_input * price.input_usd_per_mtok + usage.cache_read_input_tokens * price.input_usd_per_mtok * price.cache_read_multiplier + usage.cache_creation_input_tokens * price.input_usd_per_mtok * price.cache_write_multiplier + usage.output_tokens * price.output_usd_per_mtok) / 1_000_000
        return {"total_usd": round(total, 8), "input_usd_per_mtok": price.input_usd_per_mtok, "output_usd_per_mtok": price.output_usd_per_mtok, "price_source": price.source}

    def describe(self) -> dict[str, Any]:
        return dict(self.raw)
