from __future__ import annotations

import os
from pathlib import Path

import pytest

from gateway.ingestion.config import (
    EmbeddingChunkConfig,
    IngestionConfig,
    IntakeConfig,
    SegmentationConfig,
    ai_code_root,
    central_database_root,
    load_root_env,
)


def test_discovers_ai_code_root_and_database(tmp_path: Path) -> None:
    root = tmp_path / "AI Code"
    nested = root / "ingestion-pipeline" / "merged-ingestion"
    nested.mkdir(parents=True)

    assert ai_code_root(nested) == root
    assert central_database_root(nested) == root / "Database"


def test_load_root_env_reads_shared_file_without_overriding_process_env(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "AI Code"
    nested = root / "ingestion-pipeline"
    nested.mkdir(parents=True)
    (root / ".env").write_text(
        "NEO4J_USERNAME=from-file\nNEO4J_PASSWORD=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NEO4J_USERNAME", "from-process")
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    assert load_root_env(nested) == root / ".env"
    assert os.environ["NEO4J_USERNAME"] == "from-process"
    assert os.environ["NEO4J_PASSWORD"] == "from-file"


def test_load_root_env_is_optional_outside_monorepo(tmp_path: Path) -> None:
    assert load_root_env(tmp_path) is None


def test_database_root_override_uses_current_name(
    tmp_path: Path, monkeypatch
) -> None:
    override = tmp_path / "database"
    monkeypatch.setenv("INGESTION_DATABASE_ROOT", str(override))

    assert central_database_root(tmp_path) == override.resolve()


def test_physical_layout_has_six_flat_storage_targets(tmp_path: Path) -> None:
    root = tmp_path / "Database"
    config = IngestionConfig(database_root=root)

    assert config.raw_root == root / "raw"
    assert config.envelope_root == root / "envelopes"
    assert config.ledger_path == root / "sqlite" / "ingestion.db"
    assert config.content_db_path == root / "sqlite" / "content.db"
    assert config.chroma_path == root / "chroma"
    assert config.neo4j_path == root / "neo4j"
    assert config.coordinator_db_path == root / "sqlite" / "coordinator.db"
    assert config.page_scanner_db_path == root / "sqlite" / "processed.db"


def test_intake_config_uses_task_profiles_and_archives_outside_drop(tmp_path: Path) -> None:
    drop = tmp_path / "drop"
    IntakeConfig(drop_folder=drop).validate()
    IntakeConfig(drop_folder=drop, cleanup_profile="ocr-cleanup-v1").validate()

    with pytest.raises(ValueError, match="cleanup_profile cannot be blank"):
        IntakeConfig(drop_folder=drop, cleanup_profile="   ").validate()
    with pytest.raises(ValueError, match="spelling_review_profile cannot be blank"):
        IntakeConfig(drop_folder=drop, spelling_review_profile="").validate()
    with pytest.raises(ValueError, match="outside drop_folder"):
        IntakeConfig(
            drop_folder=drop,
            post_publish_root=drop / "processed",
        ).validate()


def test_segmentation_and_embedding_policies_have_one_config_owner(
    tmp_path: Path,
) -> None:
    config = IngestionConfig(database_root=tmp_path / "Database")

    assert config.segmentation.chat_profile == "document-segmentation-v1"
    assert config.segmentation.required_provider == "phi4-local"
    assert config.segmentation.required_model == "phi4:14b-q4_K_M"
    assert config.segmentation.passthrough_max_words == 40
    assert config.embedding_chunks == EmbeddingChunkConfig()


@pytest.mark.parametrize(
    "policy",
    [
        SegmentationConfig(max_input_tokens=0),
        SegmentationConfig(context_sentences_before=-1),
        SegmentationConfig(max_attempts=2),
    ],
)
def test_contradictory_segmentation_settings_are_rejected(
    tmp_path: Path, policy: SegmentationConfig
) -> None:
    with pytest.raises(ValueError):
        IngestionConfig(
            database_root=tmp_path / "Database",
            segmentation=policy,
        ).validate()
