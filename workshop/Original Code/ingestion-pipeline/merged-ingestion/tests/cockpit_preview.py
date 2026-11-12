"""Manual/browser-test fixture for the Component 5 cockpit."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from cockpit.server import ReviewService, create_router
from ingestion.config import IngestionConfig, IntakeConfig
from ingestion.coordinator.stages import RunStage, StageStatus
from ingestion.coordinator.state import (
    DecisionRequest,
    PendingDecision,
    ProgressView,
    RunView,
    StageView,
)


ROOT = Path(__file__).resolve().parent
PHOTO = ROOT / "fixtures" / "cockpit-page.svg"


def view(pending: PendingDecision | None, *, terminal: str | None = None) -> RunView:
    return RunView(
        run_id="preview-run",
        stage=RunStage.COMPLETE if terminal else RunStage.INTAKE_ITEM,
        stage_status=StageStatus.DONE if terminal else StageStatus.BLOCKED,
        stages=(),
        pending=pending,
        progress=ProgressView(intake_total=1, intake_resolved=1 if terminal else 0),
        last_error=None,
        terminal_result=terminal,
    )


def book_pending(*, corrected: bool = False) -> PendingDecision:
    return PendingDecision(
        item_id=str(ROOT / "drop" / "atomic-habits"),
        item_type="book",
        gate="book_metadata",
        adapter="book_identity",
        payload={
            "folder_path": str(ROOT / "drop" / "atomic-habits"),
            "folder_name": "Atomic Habits — phone scans",
            "photo_count": 6,
            "proposed_title": "Atomic Habits",
            "proposed_author": "James Clear",
            "proposed_year": 2018,
            "cover_url": None,
            "confidence": "exact" if corrected else "fuzzy",
            "meta_source": "openlibrary",
            "resolved_slug": "atomic-habits",
        },
        allowed_actions=("confirm", "correct"),
        blocking_reason="book identity must be confirmed",
    )


def image_pending() -> PendingDecision:
    return PendingDecision(
        item_id="preview-image-hash",
        item_type="image",
        gate="content_approval",
        adapter="image_ocr",
        payload={
            "page_id": 1,
            "photo_path": str(PHOTO),
            "book_title": "Atomic Habits",
            "book_author": "James Clear",
            "page_number": 42,
            "approval_reason": "Highlighted passages require human approval.",
            "flagged_retake": False,
            "blur_score": 1.2,
            "glare_score": 0.03,
            "conf_ratio": 0.94,
            "passages": [
                {
                    "index": 0,
                    "ocr_text": "Every action you take is a vote for the person you wish to become.",
                    "edited_text": "Every action you take is a vote for the person you wish to become.",
                    "min_conf": 0.96,
                    "bbox": [95, 400, 785, 95],
                },
                {
                    "index": 1,
                    "ocr_text": "You do not rise to the level of your goals. You fall to the level of your systems.",
                    "edited_text": "You do not rise to the level of your goals. You fall to the level of your systems.",
                    "min_conf": 0.92,
                    "bbox": [95, 710, 785, 100],
                },
            ],
        },
        allowed_actions=("approve", "discard", "retake"),
        blocking_reason="approval required",
    )


class PreviewCoordinator:
    def __init__(self) -> None:
        self.current = view(book_pending())

    def start_run(self, config: IngestionConfig, *, resolver: str) -> RunView:
        del config, resolver
        self.current = view(book_pending())
        return self.current

    def submit_decision(
        self, config: IngestionConfig, decision: DecisionRequest
    ) -> RunView:
        del config
        if decision.gate == "book_metadata" and decision.action == "correct":
            self.current = view(book_pending(corrected=True))
        elif decision.gate == "book_metadata" and decision.action == "confirm":
            self.current = view(image_pending())
        else:
            self.current = view(None, terminal="complete")
        return self.current

    def retry(self, config: IngestionConfig) -> RunView:
        del config
        return self.current

    def run_report(self, config: IngestionConfig, run_id: str | None = None) -> Any:
        del config
        return {"run_id": run_id, "terminal_result": "complete"}


preview_root = ROOT / ".preview"
config = IngestionConfig(
    database_root=preview_root / "Database",
    intake=IntakeConfig(
        drop_folder=preview_root / "drop",
        vault_path=preview_root / "vault",
    ),
)
service = ReviewService(
    config,
    resolver="preview-reviewer",
    coordinator_api=PreviewCoordinator(),
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    service.start()
    yield
    service.close()


app = FastAPI(title="Ingestion router preview", lifespan=lifespan)
app.include_router(create_router(service), prefix="/api/ingestion")
