from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def central_database_root(start: Path | None = None) -> Path:
    override = os.environ.get("UNIFIED_INGESTION_DATABASE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    cursor = (start or Path.cwd()).resolve()
    for parent in (cursor, *cursor.parents):
        if parent.name == "AI Code":
            return parent / "Database"
    raise RuntimeError(
        "Cannot resolve the central Database root; set UNIFIED_INGESTION_DATABASE_ROOT"
    )


@dataclass(frozen=True)
class IngestionConfig:
    database_root: Path
    extraction_version: str = "semantic_extraction_v1"
    review_confidence_threshold: float = 0.75

    @classmethod
    def default(cls) -> "IngestionConfig":
        return cls(database_root=central_database_root())

    @property
    def runtime_root(self) -> Path:
        return self.database_root / "Ingested" / "Unified_Ingestion"

    @property
    def raw_root(self) -> Path:
        return self.database_root / "Raw Data" / "unified"

    @property
    def ledger_path(self) -> Path:
        return self.runtime_root / "ingestion.db"

    @property
    def envelope_root(self) -> Path:
        return self.runtime_root / "envelopes"

    @property
    def handoff_root(self) -> Path:
        return self.runtime_root / "handoff"

    def validate(self) -> None:
        if not 0.0 <= self.review_confidence_threshold <= 1.0:
            raise ValueError("review_confidence_threshold must be between 0 and 1")

