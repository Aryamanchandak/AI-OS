"""Smoke tests for Pydantic contracts."""
from research_mcp.contracts import (
    Annotation,
    BriefReview,
    LogicalSource,
    ModelCallRecord,
    RunRecord,
    SourceRecord,
    TriageResult,
    Provenance,
)


def test_source_record_roundtrip():
    rec = SourceRecord(
        source="arxiv",
        external_id="2301.01234",
        title="Test Paper",
        provenance=Provenance(query="test", source_tier="preprint", fetched_via="arxiv"),
    )
    assert rec.source == "arxiv"
    dumped = rec.model_dump()
    restored = SourceRecord(**dumped)
    assert restored.title == rec.title


def test_triage_result_validation():
    t = TriageResult(correctness="false", effort="deep", confidence=0.8, rationale="test")
    assert t.effort == "deep"


def test_run_record_defaults():
    r = RunRecord(mode="research", input="neuromorphic engineering")
    assert r.status == "pending"
    assert r.run_id  # not empty


def test_logical_source_defaults():
    ls = LogicalSource(fingerprint="abc123", title="A Paper")
    assert ls.external_ids == {}
    assert ls.provenance == []
