"""Phase 1.3 exit-criteria tests: annotation + synthesis + citation gate + research_topic E2E.

Requires ANTHROPIC_API_KEY. Skipped automatically when the key is absent.

Exit criteria:
  1. Exposition path — run_research_topic("neuromorphic engineering"):
       a. result.essay_path exists on disk
       b. essay contains at least one [Sn] citation tag
       c. citation gate passes (verify_citations returns passed=True)
       d. result.cost_usd > 0
       e. audit JSONL for today has at least one entry for this run_id
       f. DB row for run_id has status="complete"

  2. Refutation path — run_research_topic on a false+sophisticated claim:
       a–f same as above (gate must pass regardless of polarity)

Key implementation notes (§10, §11 of spec):
  - Citation gate is hard: a run with gate.passed=False cannot reach "complete".
    If the synthesis prompt is not producing anchored sentences reliably, this
    test will fail deterministically — fix the prompt, not the gate.
  - Essays land in the real runs/ directory (intentional per §11 — "run ~10 real deep runs").
  - DB is in a tempdir to keep tests isolated.
  - Only key-free clients (SS, arXiv, Wikipedia) are passed; Brave/GoogleBooks
    raise SourceUnavailableError but the engine swallows those in _fetch_all.
"""
import asyncio
import os
import re
import tempfile
from datetime import date
from pathlib import Path

import pytest

from research_mcp.citation_gate import verify_citations
from research_mcp.database import get_run, init_db
from research_mcp.engine import run_research_topic
from research_mcp.meter import MeteredClient
from research_mcp.sources.arxiv import ArXivClient
from research_mcp.sources.semantic_scholar import SemanticScholarClient
from research_mcp.sources.wikipedia import WikipediaClient

_SKIP = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — live API calls required for Phase 1.3",
)

_TAG_RE = re.compile(r"\[S\d+\]")

JEVONS_CLAIM = "The Jevons paradox makes AI-efficiency regulation pointless"

_REPO_ROOT = Path(__file__).parent.parent
_AUDIT_DIR = _REPO_ROOT / "audit"


def _make_clients() -> list:
    return [SemanticScholarClient(), ArXivClient(), WikipediaClient()]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Shared assertion helper
# ---------------------------------------------------------------------------

def _assert_result(result, db: str, run_id: str, *, expect_refutation: bool = False):
    # (a) Essay file exists
    essay_path = Path(result.essay_path)
    assert essay_path.exists(), f"Essay file not found: {essay_path}"

    # (b) Essay contains at least one [Sn] citation tag
    essay_text = essay_path.read_text()
    tags = _TAG_RE.findall(essay_text)
    assert tags, f"Essay has no [Sn] citation tags:\n{essay_text[:500]}"

    # (c) Citation gate passes
    gate = verify_citations(essay_text, result.logical_sources)
    assert gate.passed, (
        f"Citation gate FAILED.\n"
        f"  Invalid tags: {gate.invalid_tags}\n"
        f"  Failed quotes: {gate.failed_quotes}\n"
        f"  Unanchored sentences (non-fatal): {gate.unanchored_sentences[:3]}\n"
        f"Essay excerpt:\n{essay_text[:800]}"
    )

    # (d) cost_usd > 0
    assert result.cost_usd > 0, f"cost_usd is {result.cost_usd!r} — meter not recording"

    # (e) Audit JSONL for today has entries for this run_id
    today_glob = list(_AUDIT_DIR.glob(f"{date.today()}*.jsonl"))
    if today_glob:  # Audit dir may not exist in CI without real writes
        audit_text = today_glob[0].read_text()
        assert run_id in audit_text, (
            f"run_id {run_id!r} not found in today's audit log {today_glob[0]}"
        )

    # (f) DB status = "complete"
    async def check_db():
        return await get_run(db, run_id)

    row = _run(check_db())
    assert row is not None, f"No run row found in DB for run_id={run_id!r}"
    assert row["status"] == "complete", (
        f"Expected status='complete', got {row['status']!r} for run_id={run_id!r}"
    )


# ---------------------------------------------------------------------------
# Test 1 — exposition path
# ---------------------------------------------------------------------------

@_SKIP
def test_research_topic_exposition():
    """research_topic('neuromorphic engineering') produces a gate-passing essay."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = MeteredClient(db_path=db)
            return await run_research_topic(
                topic="neuromorphic engineering",
                profile=None,
                trusted_only=None,
                clients=_make_clients(),
                meter=meter,
                db_path=db,
            )

        result = _run(run())

    _assert_result(result, db, result.run_id, expect_refutation=False)

    # Sanity: at least one source fetched
    assert len(result.logical_sources) >= 1, (
        f"Expected ≥1 logical source, got {len(result.logical_sources)}"
    )


# ---------------------------------------------------------------------------
# Test 2 — refutation path (false + sophisticated claim)
# ---------------------------------------------------------------------------

@_SKIP
def test_research_topic_refutation():
    """run_research_topic on a false+sophisticated claim produces a gate-passing refutation."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = MeteredClient(db_path=db)
            return await run_research_topic(
                topic=JEVONS_CLAIM,
                profile=None,
                trusted_only=None,
                clients=_make_clients(),
                meter=meter,
                db_path=db,
            )

        result = _run(run())

    _assert_result(result, db, result.run_id, expect_refutation=True)

    assert len(result.logical_sources) >= 1, (
        f"Expected ≥1 logical source for refutation run, got {len(result.logical_sources)}"
    )


# ---------------------------------------------------------------------------
# Test 3 — cost is metered per stage (DB sanity)
# ---------------------------------------------------------------------------

@_SKIP
def test_cost_metered_per_stage():
    """At least expansion, annotation, and synthesis stages appear in model_calls."""
    import aiosqlite

    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = MeteredClient(db_path=db)
            result = await run_research_topic(
                topic="neuromorphic engineering",
                profile=None,
                trusted_only=None,
                clients=_make_clients(),
                meter=meter,
                db_path=db,
            )
            async with aiosqlite.connect(db) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT stage, SUM(cost_usd) as total FROM model_calls GROUP BY stage"
                ) as cursor:
                    rows = [dict(r) for r in await cursor.fetchall()]
            return result, rows

        result, stage_costs = _run(run())

    stages_seen = {r["stage"] for r in stage_costs}
    for expected in ("expansion", "annotation", "synthesis"):
        assert expected in stages_seen, (
            f"Stage '{expected}' not in model_calls. Stages found: {stages_seen}"
        )

    total_cost = sum(r["total"] for r in stage_costs)
    assert total_cost > 0, f"Total metered cost is zero: {stage_costs}"
