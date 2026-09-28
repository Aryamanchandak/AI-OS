from __future__ import annotations

from pathlib import Path

from gateway.ingestion.config import IngestionConfig
from gateway.ingestion.pipeline import UnifiedIngestionPipeline
from gateway.ingestion.sources.markdown_tree import capture_markdown_tree


def test_markdown_tree_scanner_is_sorted_read_only_and_idempotent(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "b.md").write_text("B", encoding="utf-8")
    (vault / "a.md").write_text("A", encoding="utf-8")
    ignored = vault / "ignored.txt"
    ignored.write_text("ignored", encoding="utf-8")
    original = {path: path.read_bytes() for path in vault.iterdir()}
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        first = capture_markdown_tree(pipeline, vault)
        second = capture_markdown_tree(pipeline, vault)

        origins = [pipeline.store.get_source(item.source_record_id)["origin"] for item in first]
        assert [Path(origin).name for origin in origins] == ["a.md", "b.md"]
        assert all(item.exact_duplicate for item in second)
        assert len(list(pipeline.store.rows("source_records"))) == 2

    assert {path: path.read_bytes() for path in vault.iterdir()} == original


def test_markdown_tree_records_source_relative_path(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "nested").mkdir(parents=True)
    (vault / "nested" / "note.md").write_text("hello", encoding="utf-8")
    config = IngestionConfig(database_root=tmp_path / "Database")

    with UnifiedIngestionPipeline(config) as pipeline:
        outcomes = capture_markdown_tree(pipeline, vault)
        source = pipeline.store.get_source(outcomes[0].source_record_id)
        assert '"source_relative_path": "nested/note.md"' in source["metadata_json"]


def test_markdown_tree_missing_root_raises(tmp_path: Path) -> None:
    config = IngestionConfig(database_root=tmp_path / "Database")
    with UnifiedIngestionPipeline(config) as pipeline:
        try:
            capture_markdown_tree(pipeline, tmp_path / "does-not-exist")
        except NotADirectoryError:
            pass
        else:
            raise AssertionError("expected NotADirectoryError")
