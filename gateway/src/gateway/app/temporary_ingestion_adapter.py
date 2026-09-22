"""TEMPORARY Plan-06 adapter for the sibling ingestion application.

This is the sole permitted sibling-path injection in ``gateway/src``. It is
deleted when ingestion becomes a first-class Gateway domain.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys


AI_OS_ROOT = Path(__file__).resolve().parents[4]
INGESTION_ROOT = AI_OS_ROOT / "ingestion-pipeline" / "merged-ingestion"

for import_root in (INGESTION_ROOT / "src", INGESTION_ROOT):
    value = str(import_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from cockpit.server import (  # noqa: E402
    ReviewService as ReviewService,
    config_from_environment,
    create_router,
)

from gateway.app.router_registry import RouterRegistration  # noqa: E402


def create_review_service() -> ReviewService:
    if os.environ.get("AI_OS_PREVIEW", "").strip() == "1":
        from preview import PreviewCoordinator, preview_config

        return ReviewService(
            preview_config(), resolver="preview-reviewer", coordinator_api=PreviewCoordinator()
        )

    os.environ.setdefault("INGESTION_DATABASE_ROOT", str(AI_OS_ROOT / "Database"))
    return ReviewService(
        config_from_environment(),
        resolver=os.environ.get("INGESTION_RESOLVER", "local-reviewer"),
    )


def ingestion_registration(review_service: ReviewService) -> RouterRegistration:
    return RouterRegistration(
        router=create_router(review_service),
        prefix="/api/ingestion",
        tags=("ingestion",),
    )
