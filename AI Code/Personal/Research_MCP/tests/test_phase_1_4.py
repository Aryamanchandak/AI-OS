"""Phase 1.4 exit-criteria tests: verify_claims end-to-end.

Requires ANTHROPIC_API_KEY. Skipped automatically when the key is absent.

Exit criteria:
  1. Surface-only output — run_verify_claims on a mixed-truth brief:
       a. review.surfaced contains at least one item with correctness == "false"
       b. review.passed_count >= 1
       c. every surfaced item has a non-empty essay_path
       d. every surfaced item's essay file exists on disk

  2. Silent log — silent items are written to the DB:
       a. at least one row in silent_log for this run_id
       b. review.passed_count equals the number of silent_log rows for this run_id

  3. Citations valid — every surfaced essay passes verify_citations:
       a. gate.passed == True for every surfaced item

  4. Run record — DB reflects a completed, costed run:
       a. row["status"] == "complete"
       b. row["cost_usd"] > 0

Key implementation notes:
  - split_claims is LLM-generated; claim wording drifts. Assert structural
    properties (any false-correctness item) rather than specific claim text.
  - run_verify_claims raises RuntimeError if any surfaced essay fails the
    citation gate (engine.py:99-103, 133-134). Tests intentionally let this
    propagate — a gate failure signals a synthesis-prompt regression.
  - Each test gets its own TemporaryDirectory DB for isolation.
  - Essays land in the real runs/ directory, same as Phase 1.3.
"""
import aiosqlite
import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from research_mcp.citation_gate import verify_citations
from research_mcp.database import get_run, init_db
from research_mcp.engine import run_verify_claims
from research_mcp.meter import MeteredClient
from research_mcp.sources.arxiv import ArXivClient
from research_mcp.sources.semantic_scholar import SemanticScholarClient
from research_mcp.sources.wikipedia import WikipediaClient

_SKIP = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — live API calls required for Phase 1.4",
)

BRIEF = """
Water boils at 100 degrees Celsius at sea level.
Wind turbines are giant fans that use electricity to spin.
The human brain has approximately 86 billion neurons.
The Jevons paradox proves that energy efficiency improvements always increase total energy use.
Neuromorphic chips are designed to mimic biological neural networks.
"""


def _make_clients() -> list:
    return [SemanticScholarClient(), ArXivClient(), WikipediaClient()]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Test 1 — surface-only output
# ---------------------------------------------------------------------------

@_SKIP
def test_verify_claims_surface_only():
    """run_verify_claims surfaces false claims and silences clearly-true ones."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = MeteredClient(db_path=db)
            return await run_verify_claims(
                brief=BRIEF,
                trusted_only=None,
                clients=_make_clients(),
                meter=meter,
                db_path=db,
            )

        review = _run(run())

    # (a) At least one surfaced item has correctness == "false"
    false_items = [item for item in review.surfaced if item.triage.correctness == "false"]
    assert false_items, (
        f"Expected at least one surfaced item with correctness='false'. "
        f"Surfaced items: {[(i.claim_text, i.triage.correctness) for i in review.surfaced]}"
    )

    # (b) At least one claim was silent (e.g. water boils at 100°C)
    assert review.passed_count >= 1, (
        f"Expected passed_count >= 1 (at least one silent/true claim), got {review.passed_count}"
    )

    # (c) Every surfaced item has a non-empty essay_path
    for item in review.surfaced:
        assert item.essay_path, (
            f"Surfaced item '{item.claim_text[:60]}' has empty essay_path"
        )

    # (d) Every surfaced item's essay file exists on disk
    for item in review.surfaced:
        essay = Path(item.essay_path)
        assert essay.exists(), (
            f"Essay file not found for claim '{item.claim_text[:60]}': {essay}"
        )


# ---------------------------------------------------------------------------
# Test 2 — silent log
# ---------------------------------------------------------------------------

@_SKIP
def test_verify_claims_silent_log():
    """Silent (unambiguously correct) claims are written to the silent_log table."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = MeteredClient(db_path=db)
            review = await run_verify_claims(
                brief=BRIEF,
                trusted_only=None,
                clients=_make_clients(),
                meter=meter,
                db_path=db,
            )
            async with aiosqlite.connect(db) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT claim_text, correctness FROM silent_log WHERE run_id = ?",
                    (review.run_id,),
                ) as cursor:
                    rows = [dict(r) for r in await cursor.fetchall()]
            return review, rows

        review, silent_rows = _run(run())

    # At least one row in silent_log for this run
    assert silent_rows, (
        f"Expected at least one row in silent_log for run_id={review.run_id!r}, got none"
    )

    # passed_count must exactly equal the number of silent_log rows for this run
    assert review.passed_count == len(silent_rows), (
        f"review.passed_count={review.passed_count} != len(silent_log rows)={len(silent_rows)} "
        f"for run_id={review.run_id!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 — citations valid
# ---------------------------------------------------------------------------

@_SKIP
def test_verify_claims_citations_valid():
    """Every surfaced item's essay passes the citation gate."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = MeteredClient(db_path=db)
            return await run_verify_claims(
                brief=BRIEF,
                trusted_only=None,
                clients=_make_clients(),
                meter=meter,
                db_path=db,
            )

        review = _run(run())

    for item in review.surfaced:
        essay_text = Path(item.essay_path).read_text()
        gate = verify_citations(essay_text, item.logical_sources)
        assert gate.passed, (
            f"Citation gate FAILED for claim '{item.claim_text[:60]}'.\n"
            f"  Invalid tags: {gate.invalid_tags}\n"
            f"  Failed quotes: {gate.failed_quotes}\n"
            f"  Unanchored sentences (non-fatal): {gate.unanchored_sentences[:3]}\n"
            f"Essay excerpt:\n{essay_text[:800]}"
        )


# ---------------------------------------------------------------------------
# Test 4 — run record
# ---------------------------------------------------------------------------

@_SKIP
def test_verify_claims_run_record():
    """DB run row for a completed verify-claims call is marked complete with cost > 0."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")

        async def run():
            await init_db(db)
            meter = MeteredClient(db_path=db)
            return await run_verify_claims(
                brief=BRIEF,
                trusted_only=None,
                clients=_make_clients(),
                meter=meter,
                db_path=db,
            )

        review = _run(run())

    async def check_db():
        return await get_run(db, review.run_id)

    row = _run(check_db())

    assert row is not None, f"No run row found in DB for run_id={review.run_id!r}"
    assert row["status"] == "complete", (
        f"Expected status='complete', got {row['status']!r} for run_id={review.run_id!r}"
    )
    assert row["cost_usd"] > 0, (
        f"cost_usd is {row['cost_usd']!r} — meter not recording for run_id={review.run_id!r}"
    )
