"""Adaptive engine: the central control flow wiring all stages together.

Two entry points:
  - run_research_topic  → always deep, exposition
  - run_verify_claims   → full range triage per claim; batched by brief
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

from .annotation import annotate_sources
from .citation_gate import verify_citations
from .contracts import (
    BriefReview,
    LogicalSource,
    ResearchResult,
    RunRecord,
    SurfacedItem,
    TriageResult,
)
from .database import (
    get_annotations_for_source_ids,
    insert_run,
    link_source_to_run,
    log_silent_item,
    save_annotation,
    update_run_status,
    upsert_logical_source,
)
from .dedup import check_existing, merge_into_logical_sources
from .contracts import Annotation
from .expansion import expand_topic
from .meter import MeteredClient
from .sources.base import SourceClient, SourceUnavailableError
from .synthesis import synthesize
from .triage import split_claims, triage_item

_REPO_ROOT = Path(__file__).parent.parent.parent
_RUNS_DIR = _REPO_ROOT / "runs"


async def _fetch_all(
    queries: list[str],
    clients: list[SourceClient],
    trusted_only: bool | None,
    profile: str | None,
) -> list:
    """Run all queries against all available clients; ignore unavailable ones."""
    tasks = []
    for q in queries:
        for client in clients:
            kwargs: dict = {}
            if trusted_only is not None:
                kwargs["trusted_sources_only"] = trusted_only
            if profile:
                kwargs["category"] = profile
            tasks.append(client.search(q, **kwargs))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    records = []
    for r in results:
        if isinstance(r, Exception):
            continue  # log silently; SourceUnavailableError is expected for keyed clients
        records.extend(r)
    return records


async def _pipeline_deep(
    topic: str,
    triage: TriageResult,
    clients: list[SourceClient],
    trusted_only: bool | None,
    profile: str | None,
    meter: MeteredClient,
    db_path: str,
    run_id: str,
    run_dir: Path,
) -> tuple[list[LogicalSource], str]:
    """Expand → fetch → dedup → annotate → synthesize → gate. Returns (sources, essay_path)."""
    queries = await expand_topic(topic, triage, meter, run_id)
    raw_records = await _fetch_all(queries, clients, trusted_only, profile)

    if not raw_records:
        raise RuntimeError(f"No sources found for run {run_id}")

    logical_sources = merge_into_logical_sources(raw_records)

    existing_map = await check_existing(db_path, [s.fingerprint for s in logical_sources])
    for src in logical_sources:
        await upsert_logical_source(db_path, src)
        await link_source_to_run(db_path, run_id, existing_map.get(src.fingerprint, src.id))

    new_sources = [s for s in logical_sources if s.fingerprint not in existing_map]
    new_annotations = await annotate_sources(topic, new_sources, meter, run_id) if new_sources else []
    for ann in new_annotations:
        await save_annotation(db_path, ann.logical_source_id, run_id, ann.relevance, ann.key_findings, ann.credibility_tier)

    known_ids = [existing_map[s.fingerprint] for s in logical_sources if s.fingerprint in existing_map]
    cached_rows = await get_annotations_for_source_ids(db_path, known_ids)
    cached_annotations = [
        Annotation(
            logical_source_id=r["logical_source_id"],
            run_id=r["run_id"],
            relevance=r["relevance"],
            key_findings=__import__("json").loads(r["key_findings"]),
            credibility_tier=r["credibility_tier"],
        )
        for r in cached_rows
    ]
    annotations = new_annotations + cached_annotations

    essay = await synthesize(topic, triage, logical_sources, annotations, meter, run_id, run_dir)

    gate = verify_citations(essay, logical_sources)
    if not gate.passed:
        raise RuntimeError(
            f"Citation gate failed for run {run_id}. "
            f"Invalid tags: {gate.invalid_tags}. Failed quotes: {gate.failed_quotes}"
        )

    essay_path = str(run_dir / "essay.md")
    return logical_sources, essay_path


async def _pipeline_light(
    claim: str,
    clients: list[SourceClient],
    trusted_only: bool | None,
    meter: MeteredClient,
    db_path: str,
    run_id: str,
    run_dir: Path,
    triage: TriageResult,
) -> tuple[list[LogicalSource], str]:
    """Single fetch → dedup → synthesize (correction). Returns (sources, essay_path)."""
    raw_records = await _fetch_all([claim], clients, trusted_only, None)
    if not raw_records:
        raw_records = []

    logical_sources = merge_into_logical_sources(raw_records) if raw_records else []

    existing_map = await check_existing(db_path, [s.fingerprint for s in logical_sources])
    for src in logical_sources:
        await upsert_logical_source(db_path, src)
        await link_source_to_run(db_path, run_id, existing_map.get(src.fingerprint, src.id))

    new_sources = [s for s in logical_sources if s.fingerprint not in existing_map]
    new_annotations = await annotate_sources(claim, new_sources, meter, run_id) if new_sources else []
    for ann in new_annotations:
        await save_annotation(db_path, ann.logical_source_id, run_id, ann.relevance, ann.key_findings, ann.credibility_tier)

    known_ids = [existing_map[s.fingerprint] for s in logical_sources if s.fingerprint in existing_map]
    cached_rows = await get_annotations_for_source_ids(db_path, known_ids)
    cached_annotations = [
        Annotation(
            logical_source_id=r["logical_source_id"],
            run_id=r["run_id"],
            relevance=r["relevance"],
            key_findings=__import__("json").loads(r["key_findings"]),
            credibility_tier=r["credibility_tier"],
        )
        for r in cached_rows
    ]
    annotations = new_annotations + cached_annotations

    essay = await synthesize(claim, triage, logical_sources, annotations, meter, run_id, run_dir,
                             model="claude-sonnet-4-6", stage="correction")
    gate = verify_citations(essay, logical_sources)
    if not gate.passed:
        raise RuntimeError(f"Citation gate failed (light) for run {run_id}: {gate.invalid_tags}")

    return logical_sources, str(run_dir / "essay.md")


async def run_research_topic(
    topic: str,
    profile: str | None,
    trusted_only: bool | None,
    clients: list[SourceClient],
    meter: MeteredClient,
    db_path: str,
) -> ResearchResult:
    run = RunRecord(mode="research", input=topic)
    run_dir = _RUNS_DIR / run.run_id
    await insert_run(db_path, run)
    await update_run_status(db_path, run.run_id, "running")

    try:
        triage = TriageResult(correctness="topic", effort="deep", confidence=1.0, rationale="research_topic always deep")
        sources, essay_path = await _pipeline_deep(
            topic, triage, clients, trusted_only, profile, meter, db_path, run.run_id, run_dir
        )
        await update_run_status(db_path, run.run_id, "complete", finished_at=datetime.utcnow())

        run_data = await __import__("research_mcp.database", fromlist=["get_run"]).get_run(db_path, run.run_id)
        cost = float(run_data["cost_usd"]) if run_data else 0.0

        return ResearchResult(
            run_id=run.run_id,
            essay_path=essay_path,
            logical_sources=sources,
            cost_usd=cost,
        )
    except Exception:
        await update_run_status(db_path, run.run_id, "failed", finished_at=datetime.utcnow())
        raise


async def run_verify_presplit(
    claims: list[str],
    trusted_only: bool | None,
    clients: list[SourceClient],
    meter: MeteredClient,
    db_path: str,
    floor_effort: str = "light",
) -> BriefReview:
    """
    Like run_verify_claims but accepts pre-split claims (skips the split_claims stage).

    Designed for callers (e.g. podcast-brief) that already have structured claims and
    want to preserve their provenance rather than re-parsing from raw text.

    floor_effort="light"  → silent claims are upgraded to light (recommended when the
                            caller has already pre-filtered claims worth researching).
    floor_effort="silent" → silent claims are logged and excluded from surfaced[].

    Per-claim try/except: individual failures degrade gracefully to a SurfacedItem with
    essay_path=None and empty logical_sources, rather than killing the whole batch.
    """
    run = RunRecord(mode="verify", input="\n".join(claims))
    await insert_run(db_path, run)
    await update_run_status(db_path, run.run_id, "running")

    try:
        triages = await asyncio.gather(*[triage_item(c, meter, run.run_id) for c in claims])

        if floor_effort == "light":
            triages = [
                TriageResult(
                    correctness=t.correctness,
                    effort="light",
                    confidence=t.confidence,
                    rationale=t.rationale,
                )
                if t.effort == "silent" else t
                for t in triages
            ]

        surfaced: list[SurfacedItem] = []
        passed_count = 0

        for idx, (claim, triage) in enumerate(zip(claims, triages)):
            if triage.effort == "silent":
                await log_silent_item(
                    db_path, claim, triage.correctness, triage.effort,
                    triage.confidence, triage.rationale, run.run_id,
                )
                passed_count += 1
                surfaced.append(
                    SurfacedItem(claim_text=claim, triage=triage, essay_path=None, logical_sources=[])
                )
                continue

            safe_slug = claim[:30].replace("/", "_").replace(" ", "_")
            claim_run_dir = _RUNS_DIR / run.run_id / "claims" / f"{idx:03d}_{safe_slug}"

            try:
                if triage.effort == "deep":
                    sources, essay_path = await _pipeline_deep(
                        claim, triage, clients, trusted_only, None,
                        meter, db_path, run.run_id, claim_run_dir,
                    )
                else:
                    sources, essay_path = await _pipeline_light(
                        claim, clients, trusted_only, meter, db_path,
                        run.run_id, claim_run_dir, triage,
                    )
            except Exception:
                sources, essay_path = [], None

            surfaced.append(
                SurfacedItem(claim_text=claim, triage=triage, essay_path=essay_path, logical_sources=sources)
            )

        await update_run_status(db_path, run.run_id, "complete", finished_at=datetime.utcnow())
        return BriefReview(surfaced=surfaced, passed_count=passed_count, run_id=run.run_id)

    except Exception:
        await update_run_status(db_path, run.run_id, "failed", finished_at=datetime.utcnow())
        raise


async def run_verify_claims(
    brief: str,
    trusted_only: bool | None,
    clients: list[SourceClient],
    meter: MeteredClient,
    db_path: str,
) -> BriefReview:
    run = RunRecord(mode="verify", input=brief)
    await insert_run(db_path, run)
    await update_run_status(db_path, run.run_id, "running")

    try:
        claims = await split_claims(brief, meter, run.run_id)
        triages = await asyncio.gather(*[triage_item(c, meter, run.run_id) for c in claims])

        surfaced: list[SurfacedItem] = []
        passed_count = 0

        for claim, triage in zip(claims, triages):
            if triage.effort == "silent":
                await log_silent_item(db_path, claim, triage.correctness, triage.effort, triage.confidence, triage.rationale, run.run_id)
                passed_count += 1
                continue

            claim_run_dir = _RUNS_DIR / run.run_id / "claims" / claim[:40].replace("/", "_")

            if triage.effort == "deep":
                sources, essay_path = await _pipeline_deep(
                    claim, triage, clients, trusted_only, None, meter, db_path, run.run_id, claim_run_dir
                )
            else:  # light
                sources, essay_path = await _pipeline_light(
                    claim, clients, trusted_only, meter, db_path, run.run_id, claim_run_dir, triage
                )

            surfaced.append(SurfacedItem(claim_text=claim, triage=triage, essay_path=essay_path, logical_sources=sources))

        await update_run_status(db_path, run.run_id, "complete", finished_at=datetime.utcnow())
        return BriefReview(surfaced=surfaced, passed_count=passed_count, run_id=run.run_id)

    except Exception:
        await update_run_status(db_path, run.run_id, "failed", finished_at=datetime.utcnow())
        raise
