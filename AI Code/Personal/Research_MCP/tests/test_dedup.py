"""Unit tests for deduplication logic."""
from research_mcp.contracts import Provenance, SourceRecord
from research_mcp.dedup import (
    content_fingerprint,
    merge_into_logical_sources,
    normalize_id,
)


def _prov(source: str) -> Provenance:
    return Provenance(query="test", source_tier="academic", fetched_via=source)


def _rec(source: str, ext_id: str, title: str, authors: list[str] | None = None, year: str | None = None) -> SourceRecord:
    return SourceRecord(
        source=source,
        external_id=ext_id,
        title=title,
        authors=authors or ["Smith, J"],
        published=year or "2023",
        provenance=_prov(source),
    )


def test_normalize_arxiv_strips_version():
    assert normalize_id("arxiv", "2301.01234v2") == "2301.01234"
    assert normalize_id("arxiv", "2301.01234v10") == "2301.01234"


def test_normalize_doi_lowercase():
    assert normalize_id("semantic_scholar", "10.1234/TEST") == "10.1234/test"


def test_fingerprint_is_stable():
    fp1 = content_fingerprint("A Great Paper", "Smith, J", "2023")
    fp2 = content_fingerprint("A Great Paper", "Smith, J", "2023")
    assert fp1 == fp2


def test_fingerprint_ignores_case_and_whitespace():
    fp1 = content_fingerprint("A Great Paper", "Smith, J", "2023")
    fp2 = content_fingerprint("a great paper", "smith, j", "2023")
    assert fp1 == fp2


def test_merge_collapses_same_paper():
    """Same paper arriving from S2 (DOI) and arXiv should collapse to one LogicalSource."""
    records = [
        _rec("semantic_scholar", "10.1234/test.paper", "Neural Architecture Search", ["Smith, J"], "2023"),
        _rec("arxiv", "2301.01234v2", "Neural Architecture Search", ["Smith, J"], "2023"),
    ]
    sources = merge_into_logical_sources(records)
    assert len(sources) == 1
    ls = sources[0]
    assert "semantic_scholar" in ls.external_ids
    assert "arxiv" in ls.external_ids
    assert normalize_id("arxiv", "2301.01234v2") == ls.external_ids["arxiv"]


def test_merge_keeps_distinct_papers():
    records = [
        _rec("arxiv", "2301.00001", "Paper Alpha", ["Jones, A"], "2022"),
        _rec("arxiv", "2301.00002", "Paper Beta", ["Brown, B"], "2023"),
    ]
    sources = merge_into_logical_sources(records)
    assert len(sources) == 2


def test_merge_preserves_excerpt():
    rec = _rec("wikipedia", "Neuromorphic_engineering", "Neuromorphic engineering", [], "2023")
    rec.raw_excerpt = "Neuromorphic engineering is a concept developed by Carver Mead."
    sources = merge_into_logical_sources([rec])
    assert sources[0].raw_excerpt == rec.raw_excerpt
