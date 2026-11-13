"""C5 — rate limiting and a cost circuit breaker for the HTTP data plane.

Invariant 8 (every run must have hard limits on time, tokens, tool calls,
and cost) originally had no real "run" to scope to: the S11 agent runtime
is still a stub (see routes/channels.py) that just echoes messages back,
so this collapsed invariant 8 to the coarsest defensible scope -- a
per-caller requests-per-minute bucket, and a gateway-wide daily USD cost
ceiling that trips a circuit breaker (503) once crossed.

Post-audit hardening: a "run" DOES exist at the /v1/chat data-plane layer
-- one HTTP request is one provider call attempt (or a bounded retry
chain of them). That was still missing four things a caller fully
controlled with no ceiling: `max_tokens` (now capped in
glc.llm_schemas.ChatRequest/VisionRequest), batch fan-out size/concurrency
(now capped in glc.llm_schemas.BatchChatRequest), a wall-clock execution
timeout per call (`run_timeout_seconds` below, wrapping
routes/chat.py::chat's whole retry loop in `asyncio.wait_for`), and a
per-run cost estimate ceiling (`enforce_per_run_cost_ceiling` below,
checked BEFORE dispatching using the same token estimate already computed
for provider selection) -- distinct from the daily ceiling, which only
catches overspend in aggregate, after the fact, across many runs.

All of the above are enforced as router-level FastAPI dependencies (like
`require_bearer_token`), so any future `/v1/*` route added to an
already-gated router is covered by construction rather than needing its
own opt-in.

Known limitation (documented, not silently ignored — same posture as
Phase 4's single shared bearer token): with one shared credential, there is
no true per-tenant identity to key the rate limiter on. This keys on the
caller's source IP instead, the closest proxy for "caller" available.
Behind a shared NAT/proxy, distinct callers collapse into one bucket; fixing
that needs per-caller credentials (Phase 4's noted gap), which is a bigger
change than Part 1's floor requires.

In-memory state (the token buckets) is process-local, which is only sound
because A6 pins the gateway Function to exactly one container
(min_containers=1, max_containers=1) — see modal_app.py. Multiple gateway
containers would each keep their own bucket, silently multiplying the
effective rate limit.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request


class TokenBucket:
    """Per-key token bucket. `capacity` tokens, refilled continuously at
    `refill_per_second`; each call to `allow()` costs one token."""

    def __init__(self, capacity: int, refill_per_second: float) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._tokens: dict[str, float] = defaultdict(lambda: float(capacity))
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, str]:
        now = time.time()
        with self._lock:
            last = self._last.get(key, now)
            elapsed = max(0.0, now - last)
            tokens = min(self.capacity, self._tokens[key] + elapsed * self.refill_per_second)
            if tokens < 1.0:
                self._tokens[key] = tokens
                self._last[key] = now
                return False, f"rate limit exceeded ({self.capacity}/min for this caller)"
            self._tokens[key] = tokens - 1.0
            self._last[key] = now
            return True, ""


_bucket: TokenBucket | None = None


def get_data_plane_bucket() -> TokenBucket:
    global _bucket
    if _bucket is None:
        rpm = int(os.getenv("GLC_DATA_PLANE_RPM", "60"))
        _bucket = TokenBucket(capacity=rpm, refill_per_second=rpm / 60.0)
    return _bucket


def reset_for_tests() -> None:
    """Test-only: force a fresh bucket (and re-read env) between tests, the
    same pattern conftest.py already uses for the WS rate limiter / pairing
    store singletons."""
    global _bucket
    _bucket = None


def _caller_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request) -> None:
    bucket = get_data_plane_bucket()
    ok, why = bucket.allow(_caller_key(request))
    if not ok:
        raise HTTPException(429, why)


def _daily_ceiling_usd() -> float:
    return float(os.getenv("GLC_DAILY_COST_CEILING_USD", "5.0"))


def run_timeout_seconds() -> float:
    """Wall-clock execution-time ceiling for one /v1/chat run (the whole
    provider-selection + retry loop in routes/chat.py, wrapped in
    `asyncio.wait_for`). Before this, a provider call that simply hung
    (no timeout, no error, nothing) blocked that request forever — no
    ceiling anywhere in the request path caught it."""
    return float(os.getenv("GLC_RUN_TIMEOUT_SECONDS", "60"))


def _per_run_cost_ceiling_usd() -> float:
    return float(os.getenv("GLC_PER_RUN_COST_CEILING_USD", "2.0"))


def enforce_per_run_cost_ceiling(estimated_tokens: int) -> None:
    """Reject a single request outright if its own estimated cost alone
    would exceed a per-run ceiling — distinct from `enforce_cost_budget`'s
    rolling daily aggregate, which only ever catches overspend after many
    runs have already happened. Conservative by construction: since the
    provider hasn't been picked yet at this point in the request (this
    runs before routing), it prices the estimate against the MOST
    expensive configured provider/direction, not whichever one actually
    ends up serving the call — a request that's fine on a $0 free-tier
    provider but would be expensive on a paid one is still capped here."""
    ceiling = _per_run_cost_ceiling_usd()
    if ceiling <= 0:
        return

    from glc.pricing import PRICING_USD_PER_MTOK

    worst_rate = max((max(p_in, p_out) for p_in, p_out in PRICING_USD_PER_MTOK.values()), default=0.0)
    worst_case_usd = round((estimated_tokens / 1_000_000) * worst_rate, 6)
    if worst_case_usd > ceiling:
        raise HTTPException(
            413,
            f"estimated run cost (${worst_case_usd:.4f}, worst-case across configured "
            f"providers for ~{estimated_tokens} tokens) exceeds the per-run ceiling of "
            f"${ceiling:.2f}",
        )


def enforce_cost_budget() -> None:
    """Circuit breaker: if today's actual provider spend (real token counts
    already logged by db.log_call, priced via glc.pricing) has crossed the
    ceiling, refuse new data-plane requests with 503 until the day rolls
    over. A ceiling of 0 (or less) disables the breaker — an explicit
    opt-out, not the default."""
    ceiling = _daily_ceiling_usd()
    if ceiling <= 0:
        return

    from glc import db, pricing

    spent = 0.0
    for provider, row in db.aggregate(call_role="worker").items():
        spent += pricing.estimate_usd(provider, row.get("in_tok") or 0, row.get("out_tok") or 0)
    if spent >= ceiling:
        raise HTTPException(
            503,
            f"daily cost ceiling reached (${ceiling:.2f}); circuit breaker tripped until the day rolls over",
        )
