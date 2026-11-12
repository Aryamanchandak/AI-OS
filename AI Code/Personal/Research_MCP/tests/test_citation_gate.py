"""Unit tests for the deterministic citation gate."""
from research_mcp.citation_gate import verify_citations
from research_mcp.contracts import LogicalSource


def _src(idx: int, excerpt: str) -> LogicalSource:
    return LogicalSource(
        fingerprint=f"fp{idx}",
        title=f"Source {idx}",
        raw_excerpt=excerpt,
    )


def test_valid_essay_passes():
    sources = [_src(1, "Neuromorphic chips mimic the structure of biological neural networks.")]
    essay = "Neuromorphic chips are designed to mimic biological brains. [S1]"
    result = verify_citations(essay, sources)
    assert result.passed
    assert not result.invalid_tags
    assert not result.failed_quotes


def test_invalid_tag_fails():
    sources = [_src(1, "Some text.")]
    essay = "Something interesting happened. [S2]"  # S2 doesn't exist
    result = verify_citations(essay, sources)
    assert not result.passed
    assert "[S2]" in result.invalid_tags


def test_bad_quote_fails():
    sources = [_src(1, "The actual excerpt text from the paper.")]
    essay = 'Scientists found "completely fabricated text" [S1] in the study.'
    result = verify_citations(essay, sources)
    assert not result.passed
    assert "completely fabricated text" in result.failed_quotes


def test_valid_quote_passes():
    sources = [_src(1, "The actual excerpt text from the paper.")]
    essay = 'The paper states "actual excerpt text from the paper" [S1].'
    result = verify_citations(essay, sources)
    # Should pass (quote normalises and matches)
    assert result.passed


def test_no_sources_and_no_tags_passes():
    result = verify_citations("This is a brief introduction.", [])
    assert result.passed


def test_empty_essay_passes():
    result = verify_citations("", [_src(1, "Some text.")])
    assert result.passed
