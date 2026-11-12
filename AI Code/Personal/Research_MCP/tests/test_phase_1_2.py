"""Phase 1.2 exit-criteria tests: two-axis triage + Opus expansion.

Requires ANTHROPIC_API_KEY. Skipped automatically when the key is absent.

Exit criteria (all three must hold):
  1. "wind turbines are giant fans"  → correctness=false, effort=light
  2. "neuromorphic engineering"       → correctness=topic, effort=deep, ≥3 expansion queries
  3. Jevons claim                     → correctness=false, effort=deep  (the critical one)
"""
import asyncio
import os
import tempfile

import pytest

from research_mcp.database import init_db
from research_mcp.expansion import expand_topic
from research_mcp.meter import MeteredClient
from research_mcp.triage import triage_item

_SKIP = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — live API calls required for Phase 1.2",
)

RUN_ID = "test-phase-1-2"

JEVONS_CLAIM = "The Jevons paradox makes AI-efficiency regulation pointless"


def _make_meter(db: str) -> MeteredClient:
    return MeteredClient(db_path=db)


# ---------------------------------------------------------------------------
# Case 1 — trivial false claim → light
# ---------------------------------------------------------------------------

@_SKIP
def test_wind_turbines_false_light():
    """'Wind turbines are giant fans' must be false + light."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = _make_meter(db)
            result = await triage_item("wind turbines are giant fans", meter, RUN_ID)
            return result

        t = asyncio.get_event_loop().run_until_complete(run())

    assert t.correctness == "false", f"Expected correctness=false, got {t.correctness!r}. rationale: {t.rationale}"
    assert t.effort == "light",      f"Expected effort=light, got {t.effort!r}. rationale: {t.rationale}"
    assert 0.0 <= t.confidence <= 1.0, f"confidence out of range: {t.confidence}"
    assert t.rationale, "rationale must be non-empty"


# ---------------------------------------------------------------------------
# Case 2 — topic → deep + expansion produces ≥3 queries
# ---------------------------------------------------------------------------

@_SKIP
def test_neuromorphic_topic_deep_expands():
    """'neuromorphic engineering' must be topic + deep, with ≥3 expansion queries."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = _make_meter(db)
            t = await triage_item("neuromorphic engineering", meter, RUN_ID)
            queries = await expand_topic("neuromorphic engineering", t, meter, RUN_ID)
            return t, queries

        t, queries = asyncio.get_event_loop().run_until_complete(run())

    assert t.correctness == "topic", f"Expected correctness=topic, got {t.correctness!r}. rationale: {t.rationale}"
    assert t.effort == "deep",       f"Expected effort=deep, got {t.effort!r}. rationale: {t.rationale}"
    assert 0.0 <= t.confidence <= 1.0
    assert t.rationale

    assert len(queries) >= 3, (
        f"Expansion must return ≥3 proxy queries, got {len(queries)}: {queries}"
    )
    # Each query should be a non-empty string
    for q in queries:
        assert isinstance(q, str) and q.strip(), f"Empty or non-string query: {q!r}"


# ---------------------------------------------------------------------------
# Case 3 — sophisticated false claim → MUST be deep (not light)
# ---------------------------------------------------------------------------

@_SKIP
def test_jevons_false_deep():
    """Jevons claim must be false + deep — NOT waved through as light."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = _make_meter(db)
            return await triage_item(JEVONS_CLAIM, meter, RUN_ID)

        t = asyncio.get_event_loop().run_until_complete(run())

    assert t.correctness == "false", (
        f"Expected correctness=false, got {t.correctness!r}. rationale: {t.rationale}"
    )
    assert t.effort == "deep", (
        f"CRITICAL: Jevons claim must be effort=deep (sophisticated wrong), got {t.effort!r}.\n"
        f"rationale: {t.rationale}\n"
        f"confidence: {t.confidence}\n"
        "Fix: lower _CONFIDENCE_ESCALATION_THRESHOLD in triage.py from 0.7 to 0.8 and retest."
    )
    assert 0.0 <= t.confidence <= 1.0
    assert t.rationale
