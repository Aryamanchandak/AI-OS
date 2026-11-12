from pathlib import Path

from unified_ingestion.config import IngestionConfig
from unified_ingestion.pipeline import UnifiedIngestionPipeline
from unified_ingestion.sources import capture_markdown_tree


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
