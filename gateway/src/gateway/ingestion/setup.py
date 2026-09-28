"""Construct the ingestion service during Gateway lifespan startup."""

from __future__ import annotations

import os
from pathlib import Path

from gateway.ingestion.server import ReviewService, config_from_environment

AI_OS_ROOT = Path(__file__).resolve().parents[4]


def build_review_service() -> ReviewService:
    if os.environ.get("AI_OS_PREVIEW", "").strip() == "1":
        from gateway.ingestion.preview import PreviewCoordinator, preview_config

        return ReviewService(
            preview_config(), resolver="preview-reviewer", coordinator_api=PreviewCoordinator()
        )

    root = Path(os.environ.get("INGESTION_DATABASE_ROOT", "") or AI_OS_ROOT / "Database")
    return ReviewService(
        config_from_environment(database_root=root),
        resolver=os.environ.get("INGESTION_RESOLVER", "local-reviewer"),
    )
