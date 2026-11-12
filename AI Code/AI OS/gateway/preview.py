from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir

from ingestion.config import IngestionConfig, IntakeConfig
from ingestion.coordinator.report import RunReportView
from ingestion.coordinator.stages import RunStage, StageStatus
from ingestion.coordinator.state import (
    DecisionRequest,
    PendingDecision,
    ProgressView,
    RunView,
    StageView,
)


PREVIEW_ROOT = Path(gettempdir()) / "ai-os-ingestion-preview"
PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
PHOTO = PREVIEW_ROOT / "page.svg"
if not PHOTO.exists():
    PHOTO.write_text(
        """<svg xmlns='http://www.w3.org/2000/svg' width='900' height='1200'>
<rect width='900' height='1200' fill='#f2ead8'/><rect x='110' y='150' width='680' height='900' rx='18' fill='#fffdf6'/>
<text x='165' y='260' font-family='Georgia' font-size='34' fill='#241e19'>The shape of attention</text>
<text x='165' y='350' font-family='Georgia' font-size='24' fill='#574c42'>We become what we repeatedly notice.</text>
<rect x='150' y='315' width='590' height='62' fill='#edc85a' opacity='.38'/>
<text x='165' y='470' font-family='Georgia' font-size='24' fill='#574c42'>A highlighted sentence becomes a letter</text>
<text x='165' y='510' font-family='Georgia' font-size='24' fill='#574c42'>sent forward to your future self.</text></svg>""",
        encoding="utf-8",
    )


def preview_config() -> IngestionConfig:
    drop = PREVIEW_ROOT / "drop"
    vault = PREVIEW_ROOT / "vault"
    drop.mkdir(exist_ok=True)
    vault.mkdir(exist_ok=True)
    return IngestionConfig(
        database_root=PREVIEW_ROOT / "Database",
        intake=IntakeConfig(drop_folder=drop, vault_path=vault),
    )


class PreviewCoordinator:
    def __init__(self) -> None:
        self.step = 0

    def _view(self) -> RunView:
        if self.step == 0:
            pending = PendingDecision(
                item_id="preview-book",
                item_type="book",
                gate="book_metadata",
                adapter="book_identity",
                payload={
                    "folder_name": "the-shape-of-attention",
                    "photo_count": 4,
                    "proposed_title": "The Shape of Attention",
                    "proposed_author": "Aryaman Chandak",
                    "proposed_year": 2026,
                    "cover_url": None,
                    "confidence": "fuzzy",
                    "meta_source": "local preview",
                    "resolved_slug": "the-shape-of-attention",
                },
                allowed_actions=("confirm", "correct"),
                blocking_reason="book identity must be confirmed",
            )
        elif self.step == 2:
            pending = PendingDecision(
                item_id="preview-image",
                item_type="image",
                gate="content_approval",
                adapter="image_ocr",
                payload={
                    "photo_path": str(PHOTO),
                    "book_title": "The Shape of Attention",
                    "book_author": "Aryaman Chandak",
                    "page_number": 42,
                    "approval_reason": "Highlighted passage requires approval",
                    "flagged_retake": False,
                    "blur_score": 184.2,
                    "glare_score": 0.01,
                    "conf_ratio": 0.04,
                    "passages": [
                        {
                            "index": 0,
                            "ocr_text": "We become what we repeatedly notlce.",
                            "edited_text": "We become what we repeatedly notice.",
                            "min_conf": 0.94,
                            "bbox": [150, 315, 590, 62],
                        }
                    ],
                },
                allowed_actions=("approve", "discard", "retake"),
                blocking_reason="approval required",
            )
        elif self.step == 1:
            # Component 8: a text-cleanup abbreviation occurrence, so the
            # CleanupReview screen and its C8-C6 shortcuts can be exercised in
            # a real browser without Neo4j or the local LLM gateway running.
            pending = PendingDecision(
                item_id="preview-cleanup",
                item_type="file",
                gate="cleanup",
                adapter="cleanup",
                payload={
                    "state": "review",
                    "source_kind": "text_file",
                    "phase": "abbreviation",
                    "interaction_revision": 0,
                    "working_draft_revision": 0,
                    "occurrence": {
                        "occurrence_id": "abbr-p0-5-7-1",
                        "ordinal": 1,
                        "total": 1,
                        "passage_index": None,
                        "base_start": 5,
                        "base_end": 7,
                        "current_start": 5,
                        "current_end": 7,
                        "original_text": "w/",
                        "proposed_text": "with",
                        "context_before": "Talk ",
                        "context_after": " me about the plan.",
                        "before_sentence": "",
                        "after_sentence": "",
                        "current_decision": None,
                        "mapping_id": "preview-mapping",
                        "proposal_source": "mapping:preview-mapping",
                    },
                    "authoritative_sentence": "Talk w/ me about the plan.",
                    "authoritative_working_text": "Talk w/ me about the plan.",
                    "can_continue": False,
                },
                allowed_actions=("apply_once", "apply_remember", "skip", "previous", "next"),
                blocking_reason="abbreviation review required",
            )
        else:
            pending = None
        return RunView(
            run_id="preview-run",
            stage=RunStage.INTAKE_ITEM if pending else RunStage.COMPLETE,
            stage_status=StageStatus.BLOCKED if pending else StageStatus.DONE,
            stages=(
                StageView(
                    RunStage.INTAKE_ITEM,
                    StageStatus.BLOCKED if pending else StageStatus.DONE,
                    {},
                ),
            ),
            pending=pending,
            progress=ProgressView(intake_total=3, intake_resolved=self.step),
            last_error=None,
            terminal_result="complete" if pending is None else None,
        )

    def start_run(self, config: IngestionConfig, *, resolver: str) -> RunView:
        del config, resolver
        return self._view()

    def submit_decision(self, config: IngestionConfig, decision: DecisionRequest) -> RunView:
        del config, decision
        self.step += 1
        return self._view()

    def retry(self, config: IngestionConfig) -> RunView:
        del config
        return self._view()

    def run_report(
        self, config: IngestionConfig, run_id: str | None = None
    ) -> RunReportView:
        # Mirrors the real coordinator: a RunReportView whose ``data`` is the
        # durable report body written by Coordinator._finish. Returning a bare
        # dict here would let preview-backed tests pass against a shape the
        # production path never produces.
        del config
        resolved = str(run_id or "preview-run")
        return RunReportView(
            run_id=resolved,
            path=PREVIEW_ROOT / "reports" / f"{resolved}.json",
            data={
                "run_id": resolved,
                "terminal_result": "complete",
                "failed_from": None,
                "last_error": None,
                "stages": [
                    {"stage": "intake_item", "status": "done", "detail": {"items": 2}},
                    {"stage": "capture_obsidian", "status": "done", "detail": {}},
                    {"stage": "dispatch_retry", "status": "skipped", "detail": {}},
                ],
                "intake": {
                    "discovered": 2,
                    "published": 2,
                    "discarded": 0,
                    "retake": 0,
                    "duplicate": 0,
                    "failed": 0,
                    "items": [
                        {
                            "source_path": str(PHOTO),
                            "outcome": "published",
                            "note_path": "vault/the-shape-of-attention.md",
                        }
                    ],
                    "gates": [{"gate": "content_approval", "action": "approve"}],
                },
                "vault_notes_written": ["vault/the-shape-of-attention.md"],
                "capture": [],
                "capture_counts": {"total": 1, "new": 1, "duplicate": 0},
                "processing": [],
                "processing_counts": {"published": 1},
                "review": {"approve": 1, "edit": 0, "reject": 0, "still_blocked": 0},
                "dispatch_counts": {},
                "retryable_failures": [],
                "discrepancies": [],
                "progress": {
                    "intake_total": 2,
                    "intake_resolved": 2,
                    "envelopes_flagged": 0,
                    "envelopes_resolved": 0,
                },
            },
        )
