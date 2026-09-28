import pytest

from gateway.ingestion.normalization import (
    MalformedSourceError,
    normalize_origin,
    normalize_source,
)


def test_structural_normalization_extracts_frontmatter_and_stabilizes_hash() -> None:
    first = normalize_source(
        b"---\r\ntitle: Duration\r\nauthored: true\r\n---\r\nLine one   \r\nLine two\r\n",
        "HTTPS://Example.COM:443/a//b?z=2&a=1#fragment",
    )
    second = normalize_source("Line one\nLine two\n\n", "https://example.com/a/b?a=1&z=2")

    assert first.extracted_metadata == {"title": "Duration", "authored": True}
    assert first.normalized_hash == second.normalized_hash
    assert first.raw_hash != second.raw_hash
    assert first.normalized_origin == "https://example.com/a/b?a=1&z=2"


def test_malformed_utf8_and_frontmatter_are_rejected() -> None:
    with pytest.raises(MalformedSourceError):
        normalize_source(b"\xff", "note")
    with pytest.raises(MalformedSourceError):
        normalize_source("---\ntitle: broken\nbody", "note")


def test_path_origin_is_normalized() -> None:
    assert normalize_origin("~/notes/../notes/duration.md").endswith("notes/duration.md")


def test_legacy_semantic_hash_rules_are_preserved() -> None:
    first = normalize_source("* item\n\n\n\nNext", "note")
    second = normalize_source("- item\n\nNext\n", "note")
    assert first.normalized_hash == second.normalized_hash


def test_frontmatter_closing_marker_at_end_of_file_is_accepted() -> None:
    """A note that ends on its closing marker is valid, not malformed.

    It was previously quarantined: the closing marker was only ever found as
    "\\n---\\n", so a file with no trailing newline had no closing marker at
    all.
    """

    result = normalize_source("---\ntitle: Duration\n---", "note")

    assert result.extracted_metadata == {"title": "Duration"}
    assert result.normalized_content == ""


def test_empty_frontmatter_block_is_accepted() -> None:
    result = normalize_source("---\n---\nBody text\n", "note")

    assert result.extracted_metadata == {}
    assert result.normalized_content == "Body text\n"
