"""Phase 1.1 integration tests: storage + dedup (no live API calls needed)."""
import asyncio
import os
import tempfile

import pytest

from research_mcp.contracts import Provenance, SourceRecord
from research_mcp.database import (
    get_existing_fingerprints,
    init_db,
    upsert_logical_source,
)
from research_mcp.dedup import content_fingerprint, merge_into_logical_sources
from research_mcp.trusted_sources import load_trusted_sources


def _rec(source: str, ext_id: str, title: str, authors: list[str], year: str) -> SourceRecord:
    return SourceRecord(
        source=source,
        external_id=ext_id,
        title=title,
        authors=authors,
        published=year,
        provenance=Provenance(query="test", source_tier="academic", fetched_via=source),
    )


# ---------------------------------------------------------------------------
# Dedup: SS + arXiv cross-source collapse
# ---------------------------------------------------------------------------

def test_ss_arxiv_same_paper_collapses():
    """A paper on both Semantic Scholar (DOI) and arXiv collapses to one LogicalSource."""
    records = [
        _rec("semantic_scholar", "10.1016/j.neunet.2023.01.001",
             "Loihi: A neuromorphic processor", ["Davies, M", "Srinivasa, N"], "2023"),
        _rec("arxiv", "2301.05678v3",
             "Loihi: A neuromorphic processor", ["Davies, M", "Srinivasa, N"], "2023"),
    ]
    sources = merge_into_logical_sources(records)
    assert len(sources) == 1, f"Expected 1 LogicalSource, got {len(sources)}"
    ls = sources[0]
    assert "semantic_scholar" in ls.external_ids
    assert "arxiv" in ls.external_ids
    assert ls.external_ids["arxiv"] == "2301.05678"  # version stripped


def test_three_sources_same_paper_collapses():
    """Same paper from SS + arXiv + a URL (Brave) collapses to one LogicalSource."""
    records = [
        _rec("semantic_scholar", "10.1000/test.001", "Attention Is All You Need",
             ["Vaswani, A"], "2017"),
        _rec("arxiv", "1706.03762v5", "Attention Is All You Need",
             ["Vaswani, A"], "2017"),
        _rec("brave", "https://arxiv.org/abs/1706.03762", "Attention Is All You Need",
             ["Vaswani, A"], "2017"),
    ]
    sources = merge_into_logical_sources(records)
    assert len(sources) == 1
    assert len(sources[0].provenance) == 3  # all three provenance records merged


def test_distinct_papers_not_collapsed():
    records = [
        _rec("semantic_scholar", "10.1000/paper.A", "Paper Alpha", ["Jones, A"], "2021"),
        _rec("arxiv", "2101.00002", "Paper Beta", ["Brown, B"], "2022"),
    ]
    sources = merge_into_logical_sources(records)
    assert len(sources) == 2


# ---------------------------------------------------------------------------
# Database: upsert idempotency + FK correctness
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    db = str(tmp_path / "test.db")
    asyncio.get_event_loop().run_until_complete(init_db(db))
    return db


def test_upsert_idempotent(tmp_db):
    """Upserting the same LogicalSource twice does not create a second row."""
    records = [
        _rec("arxiv", "2301.00001", "Spiking Neural Networks", ["Lee, K"], "2023"),
    ]
    sources = merge_into_logical_sources(records)

    async def run():
        for src in sources:
            await upsert_logical_source(tmp_db, src)
        # Re-merge produces new UUIDs but same fingerprint
        sources2 = merge_into_logical_sources(records)
        for src in sources2:
            await upsert_logical_source(tmp_db, src)

        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            async with db.execute("SELECT COUNT(*) FROM logical_sources") as c:
                count = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM source_ids") as c:
                sid_count = (await c.fetchone())[0]
        return count, sid_count

    count, sid_count = asyncio.get_event_loop().run_until_complete(run())
    assert count == 1, f"Expected 1 logical_source, got {count}"
    assert sid_count == 1, f"Expected 1 source_id row, got {sid_count}"


def test_upsert_cross_source_fk_integrity(tmp_db):
    """After upserting a cross-source collapsed record, source_ids point to the original id."""
    records = [
        _rec("semantic_scholar", "10.1234/test", "Neuromorphic Chips", ["Mead, C"], "1990"),
        _rec("arxiv", "9001.00001v1", "Neuromorphic Chips", ["Mead, C"], "1990"),
    ]
    sources = merge_into_logical_sources(records)

    async def run():
        # First upsert
        for src in sources:
            await upsert_logical_source(tmp_db, src)
        # Second upsert with fresh UUIDs
        sources2 = merge_into_logical_sources(records)
        for src in sources2:
            await upsert_logical_source(tmp_db, src)

        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            # Only one logical source should exist
            async with db.execute("SELECT id FROM logical_sources") as c:
                ls_ids = [r[0] for r in await c.fetchall()]
            # All source_ids must reference that one id
            async with db.execute("SELECT DISTINCT logical_source_id FROM source_ids") as c:
                sid_refs = [r[0] for r in await c.fetchall()]
        return ls_ids, sid_refs

    ls_ids, sid_refs = asyncio.get_event_loop().run_until_complete(run())
    assert len(ls_ids) == 1, f"Expected 1 logical_source, got {ls_ids}"
    assert sid_refs == ls_ids, f"source_ids point to wrong id: {sid_refs} != {ls_ids}"


def test_get_existing_fingerprints(tmp_db):
    """get_existing_fingerprints returns the correct fingerprint→id map."""
    records = [
        _rec("arxiv", "2301.00001", "Paper One", ["A, B"], "2023"),
        _rec("arxiv", "2301.00002", "Paper Two", ["C, D"], "2023"),
    ]
    sources = merge_into_logical_sources(records)

    async def run():
        for src in sources:
            await upsert_logical_source(tmp_db, src)
        fps = [src.fingerprint for src in sources]
        existing = await get_existing_fingerprints(tmp_db, fps)
        return existing

    existing = asyncio.get_event_loop().run_until_complete(run())
    assert len(existing) == 2
    for src in sources:
        assert src.fingerprint in existing


# ---------------------------------------------------------------------------
# trusted_sources.yaml
# ---------------------------------------------------------------------------

def test_trusted_sources_loads():
    ts = load_trusted_sources()
    finance = ts.get_domains("finance")
    assert len(finance) > 0, "finance domains should be non-empty"
    # cross_domain always included
    assert "reuters.com" in finance


def test_trusted_sources_cross_domain():
    ts = load_trusted_sources()
    cross = ts.get_domains()  # no category → only cross_domain
    assert "reuters.com" in cross
    assert "apnews.com" in cross
    assert "factcheck.org" in cross


def test_trusted_sources_get_tier():
    ts = load_trusted_sources()
    assert ts.get_tier("https://reuters.com/article") == "cross_domain"
    assert ts.get_tier("https://sec.gov/filing") == "primary"
    assert ts.get_tier("https://bloomberg.com/news") == "press"
    assert ts.get_tier("https://some-random-blog.com") == "open_web"


def test_trusted_sources_is_trusted():
    ts = load_trusted_sources()
    assert ts.is_trusted("https://bloomberg.com/news", "finance")
    assert not ts.is_trusted("https://spammy-finance-site.xyz", "finance")


def test_trusted_sources_partial_category_name():
    ts = load_trusted_sources()
    # 'health' should match 'health_medical'
    health = ts.get_domains("health")
    assert "nih.gov" in health
    # 'legal' should match 'legal_regulatory'
    legal = ts.get_domains("legal")
    assert "ftc.gov" in legal
