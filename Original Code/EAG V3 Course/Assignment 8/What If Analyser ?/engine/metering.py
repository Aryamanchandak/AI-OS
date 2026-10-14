"""Thread-safe Gemini usage and estimated-cost accounting for one analysis.

Google returns token usage after every GenerateContent call.  This module wraps
the SDK client once at the pipeline boundary so every research, graph, debate,
verification, and narrative call is accounted for without decorating each
function independently.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass

from google import genai


class ModelCallLimitExceeded(RuntimeError):
    """The technical runaway guard stopped an abnormal number of model calls."""


@dataclass(frozen=True)
class UsageSnapshot:
    calls: int
    completed_calls: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    thinking_tokens: int
    total_tokens: int
    cost_usd: float
    cost_inr: float
    usd_to_inr: float
    max_calls: int
    pricing_note: str

    def to_dict(self) -> dict:
        return asdict(self)


class UsageLedger:
    """Accumulate usage across concurrent SDK calls belonging to one run."""

    def __init__(
        self,
        on_update: Callable[[dict], None] | None = None,
        *,
        max_calls: int | None = None,
        usd_to_inr: float | None = None,
    ) -> None:
        self.max_calls = max_calls or int(os.getenv("WHATIF_MAX_MODEL_CALLS", "30"))
        self.usd_to_inr = usd_to_inr or float(
            os.getenv("WHATIF_USD_TO_INR", "95")
        )
        self.input_rate = float(os.getenv("WHATIF_INPUT_USD_PER_M", "2.00"))
        self.cached_input_rate = float(
            os.getenv("WHATIF_CACHED_INPUT_USD_PER_M", "0.20")
        )
        self.output_rate = float(os.getenv("WHATIF_OUTPUT_USD_PER_M", "12.00"))
        self._on_update = on_update
        self._lock = threading.Lock()
        self._calls = 0
        self._completed_calls = 0
        self._input_tokens = 0
        self._cached_input_tokens = 0
        self._candidate_tokens = 0
        self._thinking_tokens = 0

    def _cost_usd_unlocked(self) -> float:
        uncached = max(0, self._input_tokens - self._cached_input_tokens)
        output = self._candidate_tokens + self._thinking_tokens
        return (
            uncached * self.input_rate
            + self._cached_input_tokens * self.cached_input_rate
            + output * self.output_rate
        ) / 1_000_000

    def _snapshot_unlocked(self) -> UsageSnapshot:
        cost_usd = self._cost_usd_unlocked()
        return UsageSnapshot(
            calls=self._calls,
            completed_calls=self._completed_calls,
            input_tokens=self._input_tokens,
            cached_input_tokens=self._cached_input_tokens,
            output_tokens=self._candidate_tokens,
            thinking_tokens=self._thinking_tokens,
            total_tokens=(
                self._input_tokens + self._candidate_tokens + self._thinking_tokens
            ),
            cost_usd=round(cost_usd, 6),
            cost_inr=round(cost_usd * self.usd_to_inr, 2),
            usd_to_inr=self.usd_to_inr,
            max_calls=self.max_calls,
            pricing_note=(
                "Estimate using Gemini 3.1 Pro Preview standard paid-tier rates "
                "for prompts up to 200k tokens; taxes, credits, and provider "
                "billing adjustments are excluded."
            ),
        )

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot_unlocked().to_dict()

    def reserve_call(self) -> None:
        """Reserve a call slot before network I/O, including parallel calls."""
        with self._lock:
            if self._calls >= self.max_calls:
                raise ModelCallLimitExceeded(
                    f"Model-call safety limit reached ({self.max_calls} calls)."
                )
            self._calls += 1
            snapshot = self._snapshot_unlocked().to_dict()
        self._emit(snapshot)

    def record_response(self, response) -> None:
        """Read SDK usage metadata after a successful GenerateContent call."""
        usage = getattr(response, "usage_metadata", None)
        with self._lock:
            self._completed_calls += 1
            if usage is not None:
                self._input_tokens += int(
                    getattr(usage, "prompt_token_count", 0) or 0
                )
                self._cached_input_tokens += int(
                    getattr(usage, "cached_content_token_count", 0) or 0
                )
                self._candidate_tokens += int(
                    getattr(usage, "candidates_token_count", 0) or 0
                )
                self._thinking_tokens += int(
                    getattr(usage, "thoughts_token_count", 0) or 0
                )
            snapshot = self._snapshot_unlocked().to_dict()
        self._emit(snapshot)

    def _emit(self, snapshot: dict) -> None:
        if self._on_update is not None:
            self._on_update(snapshot)


class _MeteredModels:
    def __init__(self, owner: "MeteredGeminiClient") -> None:
        self._owner = owner

    def generate_content(self, **kwargs):
        self._owner.ledger.reserve_call()
        response = self._owner._get_inner().models.generate_content(**kwargs)
        self._owner.ledger.record_response(response)
        return response


class MeteredGeminiClient:
    """Small SDK-compatible adapter exposing a metered ``models`` surface."""

    def __init__(
        self,
        ledger: UsageLedger,
        inner: genai.Client | None = None,
    ) -> None:
        self.ledger = ledger
        self._inner = inner
        self._inner_lock = threading.Lock()
        self.models = _MeteredModels(self)

    def _get_inner(self) -> genai.Client:
        if self._inner is None:
            with self._inner_lock:
                if self._inner is None:
                    self._inner = genai.Client()
        return self._inner
