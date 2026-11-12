from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from gateway.ingestion.config import IngestionConfig, IntakeConfig
from gateway.ingestion.coordinator.coordinator import RunCoordinator
from gateway.ingestion.coordinator.errors import (
    GateUnavailable,
    IllegalDecisionError,
    IllegalStageTransition,
    NoActiveRunError,
    RunBusyError,
)
from gateway.ingestion.coordinator.gates import BookMetadataGate, CleanupGate, ContentApprovalGate, ReviewGate
from gateway.ingestion.coordinator.preflight import (
    CheckResult,
    _folder_files,
    _probe_profile,
)
from gateway.ingestion.coordinator.stages import RunStage, StageStatus, assert_transition
from gateway.ingestion.coordinator.state import DecisionRequest
from gateway.ingestion.intake.extractors.image import ImageExtractor
from gateway.ingestion.intake.base import IntakeResult
from gateway.ingestion.models import ProcessOutcome
from gateway.ingestion.sources.page_scanner import store as page_store
from gateway.ingestion.sources.page_scanner.photo_pipeline import Passage, PhotoResult
from gateway.ingestion.text_cleanup.store import MappingRepository


class EmptyKnowledgeStore:
    def pending_reviews(self) -> list[dict[str, Any]]:
        return []

    def rows(self, table: str) -> list[dict[str, Any]]:
        assert table == "dispatches"
        return []


class EmptyKnowledgePipeline:
    def __init__(self) -> None:
        self.store = EmptyKnowledgeStore()

    def process_pending(self, limit: int = 100) -> list[Any]:
        assert limit >= 100
        return []

    def retry_dispatches(self) -> list[Any]:
        return []


@contextmanager
def empty_session(_config: IngestionConfig) -> Iterator[Any]:
    yield SimpleNamespace(pipeline=EmptyKnowledgePipeline())


def ok_preflight(_config: IngestionConfig) -> tuple[CheckResult, ...]:
    return (CheckResult("test", True, "ok", False),)


def test_local_model_preflight_allows_room_for_hidden_reasoning() -> None:
    class ReasoningModel:
        def __init__(self) -> None:
            self.max_tokens: int | None = None
            self.profile: str | None = None

        def chat(self, _prompt: str, **kwargs: Any) -> dict[str, Any]:
            self.max_tokens = kwargs["max_tokens"]
            self.profile = kwargs.get("profile")
            return {
                "text": "OK" if self.max_tokens >= 64 else "",
                "profile": self.profile,
                "provider": "gemma",
                "model": "gemma4:12b",
            }

    model = ReasoningModel()
    _probe_profile(model, "ocr-cleanup-v1")  # type: ignore[arg-type]
    assert model.max_tokens == 64
    assert model.profile == "ocr-cleanup-v1"


def empty_capture(_pipeline: object, *, vault: Path) -> list[Any]:
    assert vault.is_dir()
    return []


def make_config(tmp_path: Path) -> IngestionConfig:
    drop = tmp_path / "drop"
    vault = tmp_path / "vault"
    drop.mkdir()
    vault.mkdir()
    return IngestionConfig(
        database_root=tmp_path / "Database",
        intake=IntakeConfig(drop_folder=drop, vault_path=vault),
    )


class FakeCleanupChatClient:
    """Always answers "no spelling suggestions" -- deliberately not a fake
    that needs configuring per test. Tests exercising cleanup's own gateway
    failure/proposal behavior build their own client (see test_gates.py)."""

    def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        return {"parsed": {"edits": []}}


def default_gates(config: IngestionConfig) -> tuple[ReviewGate, ...]:
    assert config.intake is not None
    return (
        BookMetadataGate(config.page_scanner_db_path),
        CleanupGate(
            mapping_repository=MappingRepository(config.text_cleanup_db_path),
            chat_client=FakeCleanupChatClient(),
            spelling_profile=config.intake.spelling_review_profile,
        ),
        ContentApprovalGate(config.page_scanner_db_path),
    )


def coordinator(config: IngestionConfig, **kwargs: Any) -> RunCoordinator:
    kwargs.setdefault("gates", default_gates(config))
    return RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=ok_preflight,
        session_factory=empty_session,
        capture_function=empty_capture,
        **kwargs,
    )


def decision(view: Any, action: str, *, payload: dict[str, Any] | None = None) -> DecisionRequest:
    assert view.pending is not None
    return DecisionRequest(
        run_id=view.run_id,
        item_id=view.pending.item_id,
        gate=view.pending.gate,
        action=action,
        payload=payload or {},
        resolver="tester",
    )


def test_empty_intake_folder_runs_straight_to_obsidian_capture(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    run = coordinator(config)
    view = run.advance()

    assert view.stage == RunStage.COMPLETE
    assert view.terminal_result == "complete"
    discover = next(item for item in view.stages if item.stage == RunStage.DISCOVER_INTAKE)
    assert discover.status == StageStatus.SKIPPED
    assert all(item.gate != "phase_handoff" for item in [view.pending] if item)


def test_markdown_publishes_then_phase_handoff_can_stop(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "note.md").write_text(
        "# Note\n\nRepository coordinator content.", encoding="utf-8"
    )
    run = coordinator(config)

    view = run.advance()
    # Every item that reaches the real CleanupGate now always requires an
    # explicit approval press before it can publish, even a plain Markdown
    # note with zero cleanup suggestions (C8-C3) -- this removes the
    # previous auto-publish path for such items.
    assert view.pending is not None and view.pending.gate == "content_approval"
    view = run.submit_decision(decision(view, "approve"))
    assert view.stage == RunStage.INTAKE_BARRIER
    assert view.pending is not None and view.pending.gate == "phase_handoff"
    assert list(config.intake.vault_path.glob("*.md"))
    assert not (config.intake.drop_folder / "note.md").exists()

    finished = run.submit_decision(decision(view, "stop"))
    assert finished.stage == RunStage.COMPLETE
    assert (config.database_root / "reports" / f"{view.run_id}.json").is_file()
    publications = run.state_store.publications()
    assert len(publications) == 1 and publications[0].moved_at is not None


def test_phase_handoff_continue_reaches_knowledge_completion(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "note.md").write_text("# Note\n\nEnough text.")
    run = coordinator(config)
    view = run.advance()
    assert view.pending is not None and view.pending.gate == "content_approval"
    blocked = run.submit_decision(decision(view, "approve"))

    finished = run.submit_decision(decision(blocked, "continue"))
    assert finished.stage == RunStage.COMPLETE
    capture = next(item for item in finished.stages if item.stage == RunStage.CAPTURE_OBSIDIAN)
    assert capture.status == StageStatus.SKIPPED


def test_decision_for_wrong_item_is_rejected(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "note.md").write_text("# Note\n\nEnough text.")
    run = coordinator(config)
    view = run.advance()
    wrong = DecisionRequest(view.run_id, "wrong", "phase_handoff", "stop", {}, "tester")

    with pytest.raises(IllegalDecisionError, match="does not match"):
        run.submit_decision(wrong)


def test_duplicate_files_are_reported_and_only_one_is_published(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    content = "# Same\n\nByte-identical content."
    (config.intake.drop_folder / "a.md").write_text(content)
    (config.intake.drop_folder / "b.md").write_text(content)
    run = coordinator(config)
    view = run.advance()
    assert view.pending is not None and view.pending.gate == "content_approval"
    view = run.submit_decision(decision(view, "approve"))

    assert view.pending is not None
    assert view.pending.payload["published"] == 1
    assert view.pending.payload["duplicate"] == 1
    assert len(list(config.intake.vault_path.glob("*.md"))) == 1


def test_unroutable_file_and_loose_photo_fail_intake(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "unknown.bin").write_bytes(b"unknown")
    run = coordinator(config)
    failed = run.advance()
    assert failed.stage == RunStage.FAILED
    assert "unknown.bin" in (failed.last_error.message if failed.last_error else "")
    run.close()

    (config.intake.drop_folder / "unknown.bin").unlink()
    (config.intake.drop_folder / "loose.jpg").write_bytes(b"photo")
    run = coordinator(config, extractors=[ImageExtractor()])
    failed = run.advance()
    assert failed.stage == RunStage.FAILED
    assert "must be placed in a folder" in (failed.last_error.message if failed.last_error else "")


def test_preflight_failure_touches_no_intake_file(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    source = config.intake.drop_folder / "note.md"
    source.write_text("# Note\n\nEnough text.")
    run = RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=lambda _config: (
            CheckResult("dependency", False, "down", True),
        ),
    )
    view = run.advance()

    assert view.stage == RunStage.FAILED
    assert source.is_file()
    assert not list(config.intake.vault_path.glob("*.md"))
    assert run.state_store.publications() == []


def test_note_written_then_move_is_finished_on_next_start(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None and config.intake.vault_path is not None
    source = config.intake.drop_folder / "note.md"
    source.write_text("# Note\n\nEnough text.")
    note = config.intake.vault_path / "note.md"
    note.write_text(source.read_text())
    first = coordinator(config)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    publication_id = first.state_store.add_publication(source, note, digest)
    first.close()

    second = coordinator(config)
    finished = second.advance()
    assert finished.stage == RunStage.COMPLETE
    assert not source.exists()
    assert len(list(config.intake.vault_path.glob("note*.md"))) == 1
    publication = next(item for item in second.state_store.publications() if item.id == publication_id)
    assert publication.moved_at is not None


def test_second_run_is_refused_and_stale_lock_is_cleared(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    first = coordinator(config)
    with pytest.raises(RunBusyError):
        coordinator(config)
    first.close()

    lock = config.coordinator_db_path.with_suffix(".lock")
    lock.write_text(json.dumps({"pid": 999_999_999, "run_id": "dead"}))
    replacement = coordinator(config)
    assert replacement.run_id
    replacement.close()


def test_image_is_parked_approved_published_and_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    book = config.intake.drop_folder / "atomic-habits"
    book.mkdir()
    source = book / "page.jpg"
    source.write_bytes(b"photo")
    (book / ".book.json").write_text(
        json.dumps({"title": "Atomic Habits", "confidence": "exact", "confirmed": True})
    )

    def process(path: Path, *, hsv_params: object) -> PhotoResult:
        del hsv_params
        return PhotoResult(
            passages=[Passage("A highlighted passage.", [1, 2, 3, 4], 0.9)],
            blur_score=1.0,
            glare_score=0.0,
            conf_ratio=0.9,
            flagged_retake=False,
            file_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    events: list[str] = []

    def append_first(vault: Path, result: IntakeResult) -> Path:
        del result
        events.append("highlights")
        return vault / "Page Scanners" / "atomic-habits" / "atomic-habits-highlights.md"

    def write_note(vault: Path, result: IntakeResult) -> Path:
        del result
        events.append("note")
        note = vault / "page.md"
        note.write_text("approved")
        return note

    monkeypatch.setattr(
        "gateway.ingestion.coordinator.coordinator.append_book_highlight_passages",
        append_first,
    )
    run = coordinator(
        config,
        extractors=[ImageExtractor(processor=process, clean=True, cleaner=lambda value: value)],
        vault_writer=write_note,
    )
    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.gate == "content_approval"

    add_publication = run.state_store.add_publication

    def record_publication(source_path: Path, note_path: Path, content_hash: str) -> int:
        events.append("publication_row")
        return add_publication(source_path, note_path, content_hash)

    monkeypatch.setattr(run.state_store, "add_publication", record_publication)
    handoff = run.submit_decision(decision(blocked, "approve"))
    assert handoff.pending is not None and handoff.pending.gate == "phase_handoff"
    pages = page_store.get_pages(config.page_scanner_db_path)
    assert pages[0]["status"] == "published"
    assert Path(pages[0]["image_path"]).is_file()
    assert list(config.intake.vault_path.rglob("*.md"))
    assert events[:3] == ["highlights", "note", "publication_row"]


def test_photo_with_no_detected_highlights_cannot_be_silently_approved(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    book = config.intake.drop_folder / "atomic-habits"
    book.mkdir()
    source = book / "page.jpg"
    source.write_bytes(b"photo")
    (book / ".book.json").write_text(resolved_cache())

    def process(path: Path, *, hsv_params: object) -> PhotoResult:
        del hsv_params
        return PhotoResult(
            passages=[],
            blur_score=100.0,
            glare_score=0.0,
            conf_ratio=0.0,
            flagged_retake=False,
            file_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    run = coordinator(
        config,
        extractors=[
            ImageExtractor(processor=process, clean=True, cleaner=lambda value: value)
        ],
    )
    blocked = run.advance()
    assert blocked.pending is not None
    assert "no highlighted passages" in blocked.pending.blocking_reason
    assert Path(blocked.pending.payload["photo_path"]).parent.name == "_retake"

    with pytest.raises(IllegalDecisionError, match="no highlighted passages"):
        run.submit_decision(decision(blocked, "approve"))

    page = page_store.get_page(
        config.page_scanner_db_path, int(blocked.pending.payload["page_id"])
    )
    assert page is not None and page["status"] == "retake"
    assert Path(page["image_path"]).parent.name == "_retake"
    assert not list(config.intake.vault_path.rglob("*-highlights.md"))


class SequentialFixtureExtractor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def handles(self, path: Path) -> bool:
        return path.suffix == ".fixture"

    def extract(self, path: Path) -> IntakeResult:
        self.calls.append(path.name)
        approval = path.name.startswith("a")
        return IntakeResult(
            markdown_text="Extracted fixture text long enough.",
            title=path.stem,
            needs_approval=approval,
            approval_reason="fixture approval" if approval else None,
        )


def test_no_lookahead_while_a_file_is_blocked(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "a.fixture").write_text("first")
    (config.intake.drop_folder / "b.fixture").write_text("second")
    extractor = SequentialFixtureExtractor()
    run = coordinator(config, extractors=[extractor])

    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.gate == "content_approval"
    assert extractor.calls == ["a.fixture"]

    next_item = run.submit_decision(decision(blocked, "approve"))
    # "b" was not looked at while "a" was blocked; it is only extracted once
    # the coordinator actually advances to it. It also now blocks on its own
    # approval rather than auto-publishing, since every item reaching the
    # real CleanupGate requires an explicit approval press regardless of the
    # extractor's own needs_approval flag (C8-C3).
    assert extractor.calls == ["a.fixture", "a.fixture", "b.fixture"]
    assert next_item.pending is not None and next_item.pending.gate == "content_approval"

    handoff = run.submit_decision(decision(next_item, "approve"))
    assert handoff.pending is not None and handoff.pending.gate == "phase_handoff"


def test_restarting_blocked_file_reextracts_without_reparking(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    source = config.intake.drop_folder / "a.fixture"
    source.write_text("first")
    first_extractor = SequentialFixtureExtractor()
    first = coordinator(config, extractors=[first_extractor])
    blocked = first.advance()
    assert blocked.pending is not None
    page_id = int(blocked.pending.payload["page_id"])
    passage = page_store.get_passages(config.page_scanner_db_path, page_id)[0]
    page_store.update_passage(config.page_scanner_db_path, int(passage["id"]), "edited")
    first.close()

    second_extractor = SequentialFixtureExtractor()
    second = coordinator(config, extractors=[second_extractor])
    restarted = second.advance()
    assert restarted.pending is not None
    assert restarted.pending.item_id == blocked.pending.item_id
    assert second_extractor.calls == ["a.fixture"]
    assert len(page_store.get_pages(config.page_scanner_db_path)) == 1
    assert page_store.get_passages(config.page_scanner_db_path, page_id)[0]["edited_text"] == "edited"


def test_publication_rows_are_records_and_never_used_to_skip(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    source = config.intake.drop_folder / "note.md"
    source.write_text("# Note\n\nSame intentional source.")
    first = coordinator(config)
    first_view = first.advance()
    assert first_view.pending is not None and first_view.pending.gate == "content_approval"
    first_view = first.submit_decision(decision(first_view, "approve"))
    first.submit_decision(decision(first_view, "stop"))
    archived = config.database_root / "intake_processed" / "note.md"
    assert archived.is_file()

    # A second, independently-authored file that happens to share the same
    # title -- content (and therefore content hash) differs, so this proves
    # it is treated as a genuinely new item. A byte-identical re-submission
    # of the *same* source is intentionally different: the approval-bound
    # page_scanner row it shares with the first file's content hash marks it
    # already "published", and the coordinator correctly does not re-publish
    # or re-block on it (the same content-hash dedup images already rely on
    # for retakes) -- that is not what "never used to skip" is testing here.
    source.write_text("# Note\n\nA different intentional source.")

    second = coordinator(config)
    second_view = second.advance()
    assert second_view.pending is not None and second_view.pending.gate == "content_approval"
    second_view = second.submit_decision(decision(second_view, "approve"))
    assert second_view.pending is not None and second_view.pending.gate == "phase_handoff"
    assert len(second.state_store.publications()) == 2
    assert sorted(path.name for path in config.intake.vault_path.glob("*.md")) == [
        "note-2.md",
        "note.md",
    ]


class ProposalStore:
    def __init__(self) -> None:
        self.pending = True

    def pending_reviews(self) -> list[dict[str, Any]]:
        if not self.pending:
            return []
        proposal = {
            "proposal_id": "proposal-1",
            "proposal_type": "concept",
            "status": "pending",
            "original_proposal": {
                "proposal_id": "proposal-1",
                "label": "Duration",
                "model_confidence": 0.91,
                "evidence": [
                    {
                        "quote": "Duration",
                        "normalized_char_start": 0,
                        "normalized_char_end": 8,
                    }
                ],
            },
            "reasons": ["source_is_page_scanner"],
        }
        return [
            {
                "review_id": "review-1",
                "envelope_id": "envelope-1",
                "source_record_id": "source-1",
                "envelope": {
                    "origin": "/vault/Bonds.md",
                    "metadata": {
                        "vault_relative_path": "Bonds.md",
                        "origin_kind": "page_scanner",
                    },
                    "highlight_index": 0,
                    "highlight_text": "Duration",
                    "model_confidence": 0.99,
                    "review_signals": [
                        {
                            "code": "source_is_page_scanner",
                            "scope": "envelope",
                            "detail": "Scanned highlights require review",
                        },
                        {
                            "code": "matching_proposal_signal",
                            "scope": "proposal",
                            "proposal_id": "proposal-1",
                            "detail": "Belongs to the pending proposal",
                        },
                        {
                            "code": "sibling_proposal_signal",
                            "scope": "proposal",
                            "proposal_id": "proposal-2",
                            "detail": "Must not leak into this review",
                        },
                    ],
                },
                "items": [proposal],
            }
        ]

    def rows(self, table: str) -> list[dict[str, Any]]:
        assert table == "dispatches"
        return []


class ProposalPipeline:
    def __init__(self) -> None:
        self.store = ProposalStore()
        self.dispatched = False
        self.resolved_envelope_id: str | None = None

    def process_pending(self, limit: int = 100) -> list[ProcessOutcome]:
        del limit
        return [
            ProcessOutcome(
                source_record_id="source-1",
                highlight_index=0,
                envelope_id="envelope-1",
                status="review_pending",
            )
        ]

    def resolve_proposal_reviews(
        self, envelope_id: str, *args: Any, **kwargs: Any
    ) -> ProcessOutcome:
        del args, kwargs
        self.resolved_envelope_id = envelope_id
        self.store.pending = False
        self.dispatched = True
        return ProcessOutcome(
            source_record_id="source-1",
            highlight_index=0,
            envelope_id="envelope-1",
            status="processed",
            dispatched_targets=["kg"],
        )

    def retry_dispatches(self) -> list[ProcessOutcome]:
        return []


def test_flagged_proposal_pauses_then_resolution_dispatches_and_completes(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    pipeline = ProposalPipeline()

    @contextmanager
    def proposal_session(_config: IngestionConfig) -> Iterator[Any]:
        yield SimpleNamespace(pipeline=pipeline)

    run = RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=ok_preflight,
        session_factory=proposal_session,
        capture_function=empty_capture,
    )
    blocked = run.advance()
    assert blocked.stage == RunStage.PROPOSAL_REVIEW
    assert blocked.pending is not None and blocked.pending.gate == "proposal"
    assert blocked.pending.item_id == "proposal-1"
    assert blocked.pending.payload == {
        "envelope_id": "envelope-1",
        "proposal_id": "proposal-1",
        "proposal_type": "concept",
        "proposal": {
            "proposal_id": "proposal-1",
            "label": "Duration",
            "model_confidence": 0.91,
            "evidence": [
                {
                    "quote": "Duration",
                    "normalized_char_start": 0,
                    "normalized_char_end": 8,
                }
            ],
        },
        "source_note_path": "Bonds.md",
        "origin_kind": "page_scanner",
        "highlight_index": 0,
        "highlight_text": "Duration",
        "evidence_quote": "Duration",
        "evidence_start_char": 0,
        "evidence_end_char": 8,
        "proposal_confidence": 0.91,
        "envelope_confidence": 0.99,
        "signals": [
            {
                "code": "source_is_page_scanner",
                "scope": "envelope",
                "detail": "Scanned highlights require review",
            },
            {
                "code": "matching_proposal_signal",
                "scope": "proposal",
                "detail": "Belongs to the pending proposal",
                "proposal_id": "proposal-1",
            },
        ],
        "sibling_proposals": [],
        "photo_page_id": None,
        "photo_page_number": None,
        "photo_passages": [],
    }
    assert pipeline.dispatched is False

    finished = run.submit_decision(decision(blocked, "approve"))
    assert finished.stage == RunStage.COMPLETE
    assert pipeline.dispatched is True
    assert pipeline.resolved_envelope_id == "envelope-1"
    report = json.loads(
        (config.database_root / "reports" / f"{finished.run_id}.json").read_text()
    )
    assert report["processing_counts"] == {"processed": 1}
    assert report["processing"][0]["status"] == "processed"
    assert report["processing"][0]["dispatched_targets"] == ["kg"]
    assert report["dispatch_counts"] == {"kg": 1}


class MultiProposalStore:
    """One envelope with three proposals, so the sibling-proposal preview
    (payload["sibling_proposals"]) can be exercised: the active item is
    excluded, other statuses and proposal types are represented, and a
    proposal-scoped signal for a sibling must not leak into the active
    proposal's own `signals` list."""

    def pending_reviews(self) -> list[dict[str, Any]]:
        return [
            {
                "review_id": "review-1",
                "envelope_id": "envelope-1",
                "source_record_id": "source-1",
                "envelope": {
                    "origin": "/vault/Bonds.md",
                    "metadata": {
                        "vault_relative_path": "Bonds.md",
                        "origin_kind": "page_scanner",
                    },
                    "highlight_index": 0,
                    "highlight_text": "Duration measures rate sensitivity.",
                    "model_confidence": 0.99,
                    "review_signals": [],
                },
                "items": [
                    {
                        "proposal_id": "proposal-1",
                        "proposal_type": "concept",
                        "status": "pending",
                        "original_proposal": {
                            "proposal_id": "proposal-1",
                            "label": "Duration",
                            "model_confidence": 0.91,
                            "evidence": [],
                        },
                        "reasons": [],
                    },
                    {
                        "proposal_id": "proposal-2",
                        "proposal_type": "claim",
                        "status": "pending",
                        "original_proposal": {
                            "proposal_id": "proposal-2",
                            "text": "Duration measures rate sensitivity.",
                            "model_confidence": 0.85,
                            "evidence": [],
                        },
                        "reasons": [],
                    },
                    {
                        "proposal_id": "proposal-3",
                        "proposal_type": "relation",
                        "status": "approved",
                        "original_proposal": {
                            "proposal_id": "proposal-3",
                            "subject": "Duration",
                            "predicate": "measures",
                            "object": "rate sensitivity",
                            "model_confidence": 0.8,
                            "evidence": [],
                        },
                        "reasons": [],
                    },
                ],
            }
        ]

    def rows(self, table: str) -> list[dict[str, Any]]:
        assert table == "dispatches"
        return []


class MultiProposalPipeline:
    def __init__(self) -> None:
        self.store = MultiProposalStore()

    def process_pending(self, limit: int = 100) -> list[ProcessOutcome]:
        del limit
        return [
            ProcessOutcome(
                source_record_id="source-1",
                highlight_index=0,
                envelope_id="envelope-1",
                status="review_pending",
            )
        ]

    def retry_dispatches(self) -> list[ProcessOutcome]:
        return []


def test_proposal_review_lists_sibling_proposals_from_same_envelope(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)

    @contextmanager
    def proposal_session(_config: IngestionConfig) -> Iterator[Any]:
        yield SimpleNamespace(pipeline=MultiProposalPipeline())

    run = RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=ok_preflight,
        session_factory=proposal_session,
        capture_function=empty_capture,
    )
    blocked = run.advance()
    assert blocked.pending is not None
    assert blocked.pending.item_id == "proposal-1"
    siblings = blocked.pending.payload["sibling_proposals"]
    assert siblings == [
        {
            "proposal_id": "proposal-2",
            "proposal_type": "claim",
            "status": "pending",
            "summary": "Duration measures rate sensitivity.",
        },
        {
            "proposal_id": "proposal-3",
            "proposal_type": "relation",
            "status": "approved",
            "summary": "Duration measures rate sensitivity",
        },
    ]
    # The active proposal is never listed as its own sibling.
    assert all(sibling["proposal_id"] != "proposal-1" for sibling in siblings)


class PageScannerProposalStore:
    """One envelope whose highlight came from a photographed page, keyed by
    `page_scanner_id` in the envelope metadata the way
    `capture_book_highlights` (obsidian.py) actually sets it."""

    def __init__(self, page_scanner_id: int | None) -> None:
        self.page_scanner_id = page_scanner_id

    def pending_reviews(self) -> list[dict[str, Any]]:
        return [
            {
                "review_id": "review-1",
                "envelope_id": "envelope-1",
                "source_record_id": "source-1",
                "envelope": {
                    "origin": "/vault/Page Scanners/book/book-highlights.md",
                    "metadata": {
                        "vault_relative_path": "Page Scanners/book/book-highlights.md",
                        "origin_kind": "page_scanner",
                        "page_scanner_id": self.page_scanner_id,
                    },
                    "highlight_index": 0,
                    "highlight_text": "Duration measures rate sensitivity.",
                    "model_confidence": 0.99,
                    "review_signals": [],
                },
                "items": [
                    {
                        "proposal_id": "proposal-1",
                        "proposal_type": "concept",
                        "status": "pending",
                        "original_proposal": {
                            "proposal_id": "proposal-1",
                            "label": "Duration",
                            "model_confidence": 0.91,
                            "evidence": [],
                        },
                        "reasons": [],
                    },
                ],
            }
        ]

    def rows(self, table: str) -> list[dict[str, Any]]:
        assert table == "dispatches"
        return []


class PageScannerProposalPipeline:
    def __init__(self, page_scanner_id: int | None) -> None:
        self.store = PageScannerProposalStore(page_scanner_id)

    def process_pending(self, limit: int = 100) -> list[ProcessOutcome]:
        del limit
        return [
            ProcessOutcome(
                source_record_id="source-1",
                highlight_index=0,
                envelope_id="envelope-1",
                status="review_pending",
            )
        ]

    def retry_dispatches(self) -> list[ProcessOutcome]:
        return []


def test_proposal_review_includes_photo_evidence_for_a_page_scanner_highlight(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    photo = tmp_path / "page-9.jpg"
    photo.write_bytes(b"fake-jpeg-bytes")
    page_store.init_db(config.page_scanner_db_path)
    page_id = page_store.insert_page(
        config.page_scanner_db_path,
        batch="batch-1",
        author="Author",
        image_path=str(photo),
        file_hash="hash-1",
        page_number=9,
    )
    assert page_id is not None
    page_store.insert_passage(
        config.page_scanner_db_path,
        page_id,
        bbox=[10, 20, 100, 30],
        ocr_text="Duration measures rate sensitivity.",
    )
    page_store.insert_passage(
        config.page_scanner_db_path,
        page_id,
        bbox=[10, 60, 100, 30],
        ocr_text="A second passage on the same page.",
    )

    @contextmanager
    def proposal_session(_config: IngestionConfig) -> Iterator[Any]:
        yield SimpleNamespace(pipeline=PageScannerProposalPipeline(page_id))

    run = RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=ok_preflight,
        session_factory=proposal_session,
        capture_function=empty_capture,
    )
    blocked = run.advance()
    assert blocked.pending is not None
    payload = blocked.pending.payload
    assert payload["photo_page_id"] == page_id
    assert payload["photo_page_number"] == 9
    assert payload["photo_passages"] == [
        {"bbox": [10, 20, 100, 30], "ocr_text": "Duration measures rate sensitivity."},
        {"bbox": [10, 60, 100, 30], "ocr_text": "A second passage on the same page."},
    ]


def test_proposal_review_omits_photo_evidence_when_the_page_is_not_resolvable(
    tmp_path: Path,
) -> None:
    """`page_scanner_id` missing from metadata (older captures, or a typed
    note that happens to set `origin_kind` some other way) degrades to no
    photo, not an error -- the proposal is still fully reviewable on text
    alone, same as before this feature existed."""
    config = make_config(tmp_path)

    @contextmanager
    def proposal_session(_config: IngestionConfig) -> Iterator[Any]:
        yield SimpleNamespace(pipeline=PageScannerProposalPipeline(None))

    run = RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=ok_preflight,
        session_factory=proposal_session,
        capture_function=empty_capture,
    )
    blocked = run.advance()
    assert blocked.pending is not None
    payload = blocked.pending.payload
    assert payload["photo_page_id"] is None
    assert payload["photo_page_number"] is None
    assert payload["photo_passages"] == []


class RecoverableProcessingFailurePipeline(EmptyKnowledgePipeline):
    def __init__(self) -> None:
        super().__init__()
        self.recovered = False

    def process_pending(self, limit: int = 100) -> list[ProcessOutcome]:
        del limit
        if not self.recovered:
            return [
                ProcessOutcome(
                    source_record_id="source-1",
                    status="parse_failed",
                )
            ]
        return [
            ProcessOutcome(
                source_record_id="source-1",
                highlight_index=0,
                envelope_id="envelope-1",
                status="processed",
                dispatched_targets=["kg", "vector", "sqlite"],
            )
        ]


def test_unresolved_processing_failure_cannot_report_complete_and_can_retry(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    pipeline = RecoverableProcessingFailurePipeline()

    @contextmanager
    def failure_session(_config: IngestionConfig) -> Iterator[Any]:
        yield SimpleNamespace(pipeline=pipeline)

    run = RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=ok_preflight,
        session_factory=failure_session,
        capture_function=empty_capture,
    )
    failed = run.advance()
    assert failed.stage == RunStage.FAILED
    assert failed.terminal_result == "failed"
    assert failed.last_error is not None
    assert failed.last_error.stage == RunStage.PROCESS_PENDING

    failed_report = json.loads(
        (config.database_root / "reports" / f"{failed.run_id}.json").read_text()
    )
    assert failed_report["terminal_result"] == "failed"
    assert failed_report["processing_counts"] == {"parse_failed": 1}
    assert len(failed_report["retryable_failures"]) == 1

    pipeline.recovered = True
    finished = run.retry()
    assert finished.stage == RunStage.COMPLETE
    assert finished.terminal_result == "complete"
    recovered_report = json.loads(
        (config.database_root / "reports" / f"{finished.run_id}.json").read_text()
    )
    assert recovered_report["processing_counts"] == {"processed": 1}
    assert recovered_report["dispatch_counts"] == {
        "kg": 1,
        "vector": 1,
        "sqlite": 1,
    }
    assert recovered_report["retryable_failures"] == []


def test_illegal_stage_transition_raises() -> None:
    with pytest.raises(IllegalStageTransition):
        assert_transition(RunStage.PREFLIGHT, RunStage.CAPTURE_OBSIDIAN)


def test_cleanup_gate_empty_and_unavailable_are_distinct(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "note.md").write_text("# Note\n\nEnough text.")
    normal = coordinator(config)
    normal_view = normal.advance()
    intake_stage = next(
        item for item in normal_view.stages if item.stage == RunStage.INTAKE_ITEM
    )
    assert any(
        event["gate"] == "cleanup" and event["status"] == "skipped"
        for event in intake_stage.detail["gates"]
    )
    assert normal_view.pending is not None and normal_view.pending.gate == "content_approval"
    normal.submit_decision(decision(normal_view, "approve"))
    normal.close()

    # Put the archived source back for a fresh invocation.
    archived = config.database_root / "intake_processed" / "note.md"
    (config.intake.drop_folder / "note.md").write_bytes(archived.read_bytes())

    class UnavailableOnce:
        name = "cleanup"

        def __init__(self) -> None:
            self.failed = False

        def pending(self, prepared: object) -> None:
            del prepared
            if not self.failed:
                self.failed = True
                raise GateUnavailable("checker down")
            return None

        def apply(self, prepared: object, request: object) -> None:
            del prepared, request

    # An unavailable gate stops the run rather than parking an in-band pending:
    # no member of the typed pending union can carry a bare `{"error": ...}`
    # payload, so the pending this used to return could not be serialized at
    # all. It lands on the run's retryable-failure surface instead, and
    # `retry()` picks the same item back up.
    unavailable = UnavailableOnce()
    failed_run = coordinator(config, gates=[unavailable])
    failed = failed_run.advance()
    assert failed.stage == RunStage.FAILED
    assert failed.pending is None
    assert failed.last_error is not None
    assert failed.last_error.stage == RunStage.INTAKE_ITEM
    assert failed.last_error.retryable is True
    assert "checker down" in failed.last_error.message
    # The gate event still records the unavailable gate distinctly, in the
    # report a failed run writes on its way down.
    report = json.loads(
        (config.database_root / "reports" / f"{failed.run_id}.json").read_text()
    )
    gate_event = report["intake"]["gates"][-1]
    assert gate_event["gate"] == "cleanup"
    assert gate_event["status"] == "failed"
    assert gate_event["error"] == "checker down"

    resumed = failed_run.retry()
    assert resumed.pending is not None and resumed.pending.gate == "phase_handoff"


# --- Book folders -----------------------------------------------------------


def photo_processor(text: str = "A highlighted passage.", *, flagged: bool = False):
    def process(path: Path, *, hsv_params: object) -> PhotoResult:
        del hsv_params
        return PhotoResult(
            passages=[Passage(text, [1, 2, 3, 4], 0.9)],
            blur_score=1.0,
            glare_score=0.0,
            conf_ratio=0.9,
            flagged_retake=flagged,
            file_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    return process


def photo_extractor(text: str = "A highlighted passage.") -> ImageExtractor:
    return ImageExtractor(
        processor=photo_processor(text), clean=True, cleaner=lambda value: value
    )


def resolved_cache(title: str = "Atomic Habits") -> str:
    return json.dumps(
        {
            "title": title,
            "author": "James Clear",
            "confidence": "exact",
            "confirmed": True,
            "meta_source": "openlibrary",
        }
    )


def test_non_image_inside_a_book_folder_holds_the_barrier(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    book = config.intake.drop_folder / "atomic-habits"
    book.mkdir()
    (book / "page.jpg").write_bytes(b"photo")
    (book / ".book.json").write_text(resolved_cache())
    (book / "chapter.pdf").write_bytes(b"%PDF-1.4")

    run = coordinator(config, extractors=[photo_extractor()])
    failed = run.advance()
    assert failed.stage == RunStage.FAILED
    assert "chapter.pdf" in (failed.last_error.message if failed.last_error else "")
    run.close()

    (book / "chapter.pdf").unlink()
    (book / "loose").mkdir()
    nested = coordinator(config, extractors=[photo_extractor()])
    failed = nested.advance()
    assert failed.stage == RunStage.FAILED
    assert "loose" in (failed.last_error.message if failed.last_error else "")
    nested.close()


def test_book_folder_tolerates_dotfiles_retake_and_book_txt(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    book = config.intake.drop_folder / "atomic-habits"
    book.mkdir()
    (book / "page.jpg").write_bytes(b"photo")
    (book / ".book.json").write_text(resolved_cache())
    (book / ".DS_Store").write_bytes(b"finder")
    (book / "book.txt").write_text("Atomic Habits James Clear")
    (book / "_retake").mkdir()
    (book / "_retake" / "blurry.jpg").write_bytes(b"blurry")
    # Finder and sync clients leave these around the drop folder itself. A
    # hidden directory is not a book folder and a top-level dotfile is not an
    # unroutable file — either one would otherwise wedge every future run.
    (config.intake.drop_folder / ".DS_Store").write_bytes(b"finder")
    spotlight = config.intake.drop_folder / ".Spotlight-V100"
    spotlight.mkdir()
    (spotlight / "index.db").write_bytes(b"index")

    run = coordinator(config, extractors=[photo_extractor()])
    blocked = run.advance()
    assert blocked.pending is not None
    assert blocked.pending.gate == "content_approval"
    assert Path(blocked.pending.payload["photo_path"]).name == "page.jpg"


def test_book_folder_is_renamed_before_the_first_photo_publishes(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    book = config.intake.drop_folder / "atomic habits james clear"
    book.mkdir()
    (book / "page.jpg").write_bytes(b"photo")
    (book / ".book.json").write_text(resolved_cache())

    run = coordinator(config, extractors=[photo_extractor()])
    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.gate == "content_approval"
    # The rename happened before the photo was even offered for approval.
    assert (config.intake.drop_folder / "atomic-habits").is_dir()
    assert not book.exists()

    handoff = run.submit_decision(decision(blocked, "approve"))
    assert handoff.pending is not None and handoff.pending.gate == "phase_handoff"
    archived = config.database_root / "page_scanner_photos" / "atomic-habits"
    assert [path.name for path in archived.iterdir()] == ["page.jpg"]


def test_renamed_book_folder_is_not_renamed_again_on_the_next_run(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    book = config.intake.drop_folder / "atomic-habits"
    book.mkdir()
    (book / "page.jpg").write_bytes(b"photo")
    (book / ".book.json").write_text(resolved_cache())

    run = coordinator(config, extractors=[photo_extractor()])
    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.gate == "content_approval"
    assert book.is_dir()
    assert [path.name for path in config.intake.drop_folder.iterdir()] == ["atomic-habits"]


def test_book_folder_name_resolves_the_book_without_a_book_txt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gateway.ingestion.sources import book_metadata

    queries: list[str] = []

    def lookup(query: str) -> dict[str, Any]:
        queries.append(query)
        return {
            "title": "Atomic Habits",
            "author": "James Clear",
            "meta_source": "openlibrary",
            "confidence": "exact",
            "query": query,
        }

    monkeypatch.setattr(book_metadata, "_from_openlibrary", lookup)

    for name in ("Atomic Habits James Clear", "Atomic_Habits_James_Clear"):
        folder = tmp_path / name
        folder.mkdir()
        assert book_metadata.gate_status(folder) == "clear"
        assert (folder / book_metadata.CACHE_NAME).is_file()

    assert queries == ["Atomic Habits James Clear", "Atomic Habits James Clear"]

    explicit = tmp_path / "some random folder"
    explicit.mkdir()
    (explicit / book_metadata.QUERY_FILE).write_text("Atomic Habits James Clear")
    assert book_metadata.gate_status(explicit) == "clear"
    assert queries[-1] == "Atomic Habits James Clear"


def test_unrecognised_folder_name_correction_is_inspected_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gateway.ingestion.sources import book_metadata

    config = make_config(tmp_path)
    assert config.intake is not None
    book = config.intake.drop_folder / "Sapiens Yuval Noah Harari"
    book.mkdir()
    (book / "page.jpg").write_bytes(b"photo")

    run = coordinator(config, extractors=[photo_extractor()])
    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.gate == "book_metadata"
    # With no lookup answer the fallback still supplies a query, so the folder
    # is never reported as needing a cover.
    assert blocked.pending.payload["meta_source"] == "none"
    assert blocked.pending.allowed_actions == ("confirm", "correct")
    assert blocked.pending.payload["photo_count"] == 1

    monkeypatch.setattr(
        book_metadata,
        "resolve_book",
        lambda query: {
            "title": "Sapiens: A Brief History of Humankind",
            "author": "Yuval Noah Harari",
            "year": 2011,
            "isbn": "9780062316097",
            "subjects": ["History"],
            "cover_url": "https://covers.example/sapiens.jpg",
            "meta_source": "openlibrary",
            "confidence": "exact",
            "query": query,
        },
    )

    corrected = run.submit_decision(
        decision(
            blocked,
            "correct",
            payload={
                "title": "Sapiens: A Brief History of Humankind",
                "author": "Yuval Noah Harari",
            },
        )
    )
    assert corrected.pending is not None
    assert corrected.pending.gate == "book_metadata"
    assert corrected.pending.payload["proposed_year"] == 2011
    assert corrected.pending.payload["cover_url"].endswith("sapiens.jpg")
    assert corrected.pending.payload["proposed_title"] == (
        "Sapiens: A Brief History of Humankind"
    )
    assert not list(config.intake.vault_path.rglob("*.md"))
    assert not page_store.get_pages(config.page_scanner_db_path)
    assert book.is_dir()

    awaiting_approval = run.submit_decision(decision(corrected, "confirm"))
    assert awaiting_approval.pending is not None
    assert awaiting_approval.pending.gate == "content_approval"
    renamed = config.intake.drop_folder / "sapiens-a-brief-history-of-humankind"
    assert renamed.is_dir()
    assert book_metadata.gate_status(renamed) == "clear"
    assert json.loads((renamed / book_metadata.CACHE_NAME).read_text())["author"] == (
        "Yuval Noah Harari"
    )


# --- Human corrections ------------------------------------------------------


def test_content_approval_gate_saves_edited_passages_and_page_number(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    book = config.intake.drop_folder / "atomic-habits"
    book.mkdir()
    (book / "page.jpg").write_bytes(b"photo")
    (book / ".book.json").write_text(resolved_cache())

    run = coordinator(config, extractors=[photo_extractor("Teh quick brown fox.")])
    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.adapter == "image_ocr"
    passages = blocked.pending.payload["passages"]
    assert passages[0]["index"] == 0
    assert passages[0]["ocr_text"] == "Teh quick brown fox."
    assert passages[0]["edited_text"] == "Teh quick brown fox."

    run.submit_decision(
        decision(
            blocked,
            "approve",
            payload={
                "passages": [{"index": 0, "edited_text": "The quick brown fox."}],
                "page_number": 42,
            },
        )
    )

    page_id = int(blocked.pending.payload["page_id"])
    stored = page_store.get_passages(config.page_scanner_db_path, page_id)[0]
    assert stored["edited_text"] == "The quick brown fox."
    assert page_store.get_page(config.page_scanner_db_path, page_id)["page_number"] == 42
    notes = sorted(config.intake.vault_path.rglob("*.md"), key=lambda p: p.name)
    note = next(p for p in notes if not p.name.endswith("-highlights.md"))
    assert note.name == "atomic-habits-p42.md"
    assert "The quick brown fox." in note.read_text()
    assert "Teh quick" not in note.read_text()

    # T63: the approved page's corrected passage also accumulates into the
    # book's shared highlights document, alongside its own per-page note.
    highlights = next(p for p in notes if p.name.endswith("-highlights.md"))
    assert highlights.name == "atomic-habits-highlights.md"
    assert "The quick brown fox." in highlights.read_text()


def test_text_file_approval_saves_edited_markdown(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "a.fixture").write_text("first")
    run = coordinator(config, extractors=[SequentialFixtureExtractor()])

    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.adapter == "text_file"
    assert blocked.pending.allowed_actions == ("approve", "discard")
    assert blocked.pending.payload["markdown_text"] == "Extracted fixture text long enough."

    run.submit_decision(
        decision(
            blocked, "approve", payload={"markdown_text": "Corrected fixture text."}
        )
    )
    note = next(config.intake.vault_path.rglob("*.md"))
    assert "Corrected fixture text." in note.read_text()


def test_passage_edit_for_a_missing_index_is_refused(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "a.fixture").write_text("first")
    run = coordinator(config, extractors=[SequentialFixtureExtractor()])
    blocked = run.advance()

    with pytest.raises(IllegalDecisionError):
        run.submit_decision(
            DecisionRequest(
                run_id=blocked.run_id,
                item_id=blocked.pending.item_id if blocked.pending else "",
                gate="content_approval",
                action="retake",
                payload={},
                resolver="tester",
            )
        )


# --- Terminal states --------------------------------------------------------


def test_failed_run_writes_its_report_and_releases_the_lock(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "unknown.bin").write_bytes(b"unknown")
    run = coordinator(config)

    failed = run.advance()
    assert failed.stage == RunStage.FAILED
    assert failed.terminal_result == "failed"

    report = json.loads(
        (config.database_root / "reports" / f"{failed.run_id}.json").read_text()
    )
    assert report["terminal_result"] == "failed"
    assert report["failed_from"] == RunStage.DISCOVER_INTAKE.value
    assert "unknown.bin" in report["last_error"]["message"]

    lock = config.coordinator_db_path.with_suffix(".lock")
    assert not lock.exists()
    # A fix made outside the app can be followed by a clean run, with no
    # stale-lock sweep and no Python restart.
    (config.intake.drop_folder / "unknown.bin").unlink()
    replacement = coordinator(config)
    assert replacement.advance().stage == RunStage.COMPLETE


def test_completed_run_releases_the_lock_so_the_next_run_starts(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    first = coordinator(config)
    finished = first.advance()
    assert finished.stage == RunStage.COMPLETE
    assert not config.coordinator_db_path.with_suffix(".lock").exists()

    second = coordinator(config)
    assert second.advance().stage == RunStage.COMPLETE


def test_retry_after_a_failure_retakes_the_lock_and_finishes(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    unroutable = config.intake.drop_folder / "unknown.bin"
    unroutable.write_bytes(b"unknown")
    run = coordinator(config)
    assert run.advance().stage == RunStage.FAILED

    unroutable.unlink()
    resumed = run.retry()
    assert resumed.stage == RunStage.COMPLETE
    assert resumed.terminal_result == "complete"


def test_module_level_calls_without_a_run_raise_no_active_run(tmp_path: Path) -> None:
    from gateway.ingestion import coordinator as api

    config = make_config(tmp_path)
    for call in (api.advance, api.retry):
        with pytest.raises(NoActiveRunError):
            call(config)
    with pytest.raises(NoActiveRunError):
        api.submit_decision(
            config, DecisionRequest("run", "item", "gate", "approve", {}, "tester")
        )


# --- Dispatch scoping -------------------------------------------------------


class StaleDispatchStore(EmptyKnowledgeStore):
    def rows(self, table: str) -> list[dict[str, Any]]:
        assert table == "dispatches"
        return [
            {"envelope_id": "envelope-from-last-month", "target": "kg", "status": "failed"}
        ]


class StaleDispatchPipeline(EmptyKnowledgePipeline):
    def __init__(self) -> None:
        super().__init__()
        self.store = StaleDispatchStore()


def test_a_dispatch_failure_from_an_earlier_run_is_reported_not_raised(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)

    @contextmanager
    def stale_session(_config: IngestionConfig) -> Iterator[Any]:
        yield SimpleNamespace(pipeline=StaleDispatchPipeline())

    run = RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=ok_preflight,
        session_factory=stale_session,
        capture_function=empty_capture,
    )
    finished = run.advance()
    assert finished.stage == RunStage.COMPLETE

    report = json.loads(
        (config.database_root / "reports" / f"{finished.run_id}.json").read_text()
    )
    assert [
        entry["envelope_id"]
        for entry in report["retryable_failures"]
        if entry.get("target") == "kg"
    ] == ["envelope-from-last-month"]


def test_edit_decision_without_an_edited_proposal_is_rejected(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    pipeline = ProposalPipeline()

    @contextmanager
    def proposal_session(_config: IngestionConfig) -> Iterator[Any]:
        yield SimpleNamespace(pipeline=pipeline)

    run = RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=ok_preflight,
        session_factory=proposal_session,
        capture_function=empty_capture,
    )
    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.gate == "proposal"

    with pytest.raises(IllegalDecisionError, match="edited_proposal"):
        run.submit_decision(decision(blocked, "edit"))
    with pytest.raises(IllegalDecisionError, match="only valid"):
        run.submit_decision(
            decision(blocked, "approve", payload={"edited_proposal": {"label": "X"}})
        )
    assert pipeline.dispatched is False


# --- Extractor wiring -------------------------------------------------------


def test_coordinator_extractors_wire_the_cleanup_client_and_profile(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    run = RunCoordinator(config, resolver="tester", preflight_runner=ok_preflight)
    image = run._extractors[0]

    assert isinstance(image, ImageExtractor)
    assert image.clean is True
    assert image._cleanup_profile == config.intake.cleanup_profile
    assert image._metadata_client is None
    run.close()


def test_photo_archives_under_the_configured_database_root(tmp_path: Path) -> None:
    # A drop folder with no `AI Code` ancestor used to raise
    # "Cannot resolve the central Database root".
    config = make_config(tmp_path)
    assert config.intake is not None
    assert "AI Code" not in str(config.intake.drop_folder)
    book = config.intake.drop_folder / "atomic-habits"
    book.mkdir()
    (book / "page.jpg").write_bytes(b"photo")
    (book / ".book.json").write_text(resolved_cache())

    run = coordinator(config, extractors=[photo_extractor()])
    blocked = run.advance()
    run.submit_decision(decision(blocked, "approve"))

    archived = (
        config.database_root / "page_scanner_photos" / "atomic-habits" / "page.jpg"
    )
    assert archived.is_file()
    page = page_store.get_pages(config.page_scanner_db_path)[0]
    assert page["image_path"] == str(archived)


def test_photo_note_written_then_archive_failed_finishes_next_start(
    tmp_path: Path,
) -> None:
    """The Seam 1b half of the write-then-move recovery."""

    config = make_config(tmp_path)
    assert config.intake is not None and config.intake.vault_path is not None
    book = config.intake.drop_folder / "atomic-habits"
    book.mkdir()
    source = book / "page.jpg"
    source.write_bytes(b"photo")
    (book / ".book.json").write_text(resolved_cache())

    # Reach the state a crash between publish and archive leaves behind: the
    # page reviewed, the note on disk, and a publication row with no moved_at.
    first = coordinator(config, extractors=[photo_extractor()])
    blocked = first.advance()
    assert blocked.pending is not None
    page_id = int(blocked.pending.payload["page_id"])
    page_store.update_page_status(config.page_scanner_db_path, page_id, "reviewed")
    note = config.intake.vault_path / "atomic-habits-page-1.md"
    note.write_text("A highlighted passage.")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    publication_id = first.state_store.add_publication(source, note, digest)
    first.close()

    second = coordinator(config, extractors=[photo_extractor()])
    finished = second.advance()
    assert finished.stage == RunStage.COMPLETE

    archived = (
        config.database_root / "page_scanner_photos" / "atomic-habits" / "page.jpg"
    )
    assert archived.is_file()
    assert not source.exists()
    # One note, not a second one with a -2 suffix.
    assert [path.name for path in config.intake.vault_path.glob("*.md")] == [
        "atomic-habits-page-1.md"
    ]
    publication = next(
        item for item in second.state_store.publications() if item.id == publication_id
    )
    assert publication.moved_at is not None
    page = page_store.get_page(config.page_scanner_db_path, page_id)
    assert page is not None and page["status"] == "published"
    assert page["image_path"] == str(archived)


def test_preflight_counts_only_the_files_a_run_would_take_in(tmp_path: Path) -> None:
    """Preflight's file census must match `_discover`, or it demands models
    for work that does not exist.

    With `rglob("*")` a drop folder holding nothing but a `.DS_Store` and a
    book folder of already-parked `_retake/` photos looked like an image run,
    so preflight required a live local cleanup/spelling model and Apple
    Vision and refused a run with nothing to do.
    """

    drop = tmp_path / "drop"
    book = drop / "atomic-habits"
    (book / "_retake").mkdir(parents=True)
    (drop / ".DS_Store").write_bytes(b"junk")
    (book / "_retake" / "blurry.jpg").write_bytes(b"photo")
    (book / ".DS_Store").write_bytes(b"junk")
    (book / "book.txt").write_text("atomic habits")
    (drop / "book.txt").write_text("atomic habits")

    assert _folder_files(drop) == []

    page = book / "page.jpg"
    page.write_bytes(b"photo")
    note = drop / "note.md"
    note.write_text("# Note\n")

    # Preflight only asks membership questions of this list, never order.
    assert set(_folder_files(drop)) == {note, page}
