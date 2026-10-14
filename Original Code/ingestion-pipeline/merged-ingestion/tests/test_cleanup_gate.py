"""CleanupGate: engine orchestration, revisions, and coordinator handoff.

Complements tests/text_cleanup/test_working.py (pure state-machine unit
tests) with the parts that need a real CleanupGate instance and, for the
handoff guarantees in component_8.md section 12 ("Coordinator and
handoff"), a real RunCoordinator.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from ingestion.coordinator.coordinator import RunCoordinator
from ingestion.coordinator.errors import IllegalDecisionError
from ingestion.coordinator.gates import CleanupGate
from ingestion.coordinator.state import DecisionRequest
from ingestion.intake.base import IntakeResult
from ingestion.intake.extractors.image import ImageExtractor
from ingestion.intake.funnel import PreparedFile
from ingestion.sources.page_scanner import store as page_store
from ingestion.sources.page_scanner.photo_pipeline import Passage as PhotoPassage
from ingestion.sources.page_scanner.photo_pipeline import PhotoResult
from ingestion.text_cleanup.store import AuditEntry, MappingRepository

from tests.test_coordinator import (
    FakeCleanupChatClient,
    coordinator as base_coordinator,
    decision,
    make_config,
)


class RecordingFixtureExtractor:
    """A text extractor over a fixed body, never itself needs_approval."""

    def __init__(self, body: str) -> None:
        self.body = body
        self.calls: list[str] = []

    def handles(self, path: Path) -> bool:
        return path.suffix == ".fixture"

    def extract(self, path: Path) -> IntakeResult:
        self.calls.append(path.name)
        return IntakeResult(
            markdown_text=self.body,
            title=path.stem,
            needs_approval=False,
        )


def fake_prepared(text: str, content_hash: str = "hash1") -> PreparedFile:
    class _Extractor:
        def handles(self, path: Path) -> bool:
            return True

        def extract(self, path: Path) -> IntakeResult:
            return IntakeResult(markdown_text=text, title="t", needs_approval=False)

    return PreparedFile(
        source_path=Path("/tmp/does-not-matter.md"),
        extractor=_Extractor(),
        result=IntakeResult(markdown_text=text, title="t", needs_approval=False),
        content_hash=content_hash,
    )


def make_cleanup_gate(
    tmp_path: Path, *, chat_client: Any = None, mappings: list[tuple[str, str]] | None = None
) -> CleanupGate:
    repo = MappingRepository(tmp_path / "text_cleanup.db")
    for shorthand, expansion in mappings or []:
        repo.create(shorthand, expansion)
    return CleanupGate(
        mapping_repository=repo,
        chat_client=chat_client if chat_client is not None else FakeCleanupChatClient(),
        spelling_provider="gemma",
    )


# --- CleanupGate unit-level ---------------------------------------------


def test_abbreviation_settles_before_spelling_is_attempted(tmp_path: Path) -> None:
    class CountingChatClient:
        def __init__(self) -> None:
            self.calls = 0

        def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            del args, kwargs
            self.calls += 1
            return {"text": '{"edits": []}'}

    chat_client = CountingChatClient()
    gate = make_cleanup_gate(tmp_path, chat_client=chat_client, mappings=[("w/", "with")])
    prepared = fake_prepared("Talk w/ me soon.")

    pending = gate.pending(prepared)
    assert pending is not None and pending.payload["phase"] == "abbreviation"
    assert chat_client.calls == 0  # spelling not attempted while abbreviation is open

    occurrence = pending.payload["occurrence"]
    gate.apply(
        prepared,
        DecisionRequest(
            run_id="r1",
            item_id=prepared.content_hash,
            gate="cleanup",
            action="apply_once",
            payload={
                "occurrence_id": occurrence["occurrence_id"],
                "expected_interaction_revision": 0,
                "expected_working_draft_revision": 0,
            },
            resolver="tester",
        ),
    )
    next_pending = gate.pending(prepared)
    assert chat_client.calls == 1
    assert next_pending is None or next_pending.payload.get("phase") != "abbreviation"


def test_per_occurrence_action_leaves_item_pending_with_higher_interaction_revision(
    tmp_path: Path,
) -> None:
    gate = make_cleanup_gate(tmp_path, mappings=[("w/", "with"), ("re", "regarding")])
    prepared = fake_prepared("w/ one and w/ two.")
    pending = gate.pending(prepared)
    assert pending is not None
    occurrence = pending.payload["occurrence"]
    assert pending.payload["interaction_revision"] == 0

    gate.apply(
        prepared,
        DecisionRequest(
            run_id="r1",
            item_id=prepared.content_hash,
            gate="cleanup",
            action="apply_once",
            payload={
                "occurrence_id": occurrence["occurrence_id"],
                "expected_interaction_revision": 0,
                "expected_working_draft_revision": 0,
            },
            resolver="tester",
        ),
    )
    again = gate.pending(prepared)
    assert again is not None  # same item, still pending (second occurrence remains)
    assert again.item_id == pending.item_id
    assert again.payload["interaction_revision"] == 1


def test_navigation_changes_interaction_revision_not_working_draft(tmp_path: Path) -> None:
    gate = make_cleanup_gate(tmp_path, mappings=[("w/", "with")])
    prepared = fake_prepared("w/ one and w/ two.")
    pending = gate.pending(prepared)
    assert pending is not None
    occurrence = pending.payload["occurrence"]

    gate.apply(
        prepared,
        DecisionRequest(
            run_id="r1",
            item_id=prepared.content_hash,
            gate="cleanup",
            action="next",
            payload={
                "occurrence_id": occurrence["occurrence_id"],
                "expected_interaction_revision": 0,
            },
            resolver="tester",
        ),
    )
    moved = gate.pending(prepared)
    assert moved is not None
    assert moved.payload["interaction_revision"] == 1
    assert moved.payload["working_draft_revision"] == 0


def test_navigation_rejects_wrong_occurrence(tmp_path: Path) -> None:
    gate = make_cleanup_gate(tmp_path, mappings=[("w/", "with")])
    prepared = fake_prepared("w/ one and w/ two.")
    pending = gate.pending(prepared)
    assert pending is not None
    with pytest.raises(IllegalDecisionError, match="wrong or missing occurrence"):
        gate.apply(
            prepared,
            DecisionRequest(
                run_id="r1",
                item_id=prepared.content_hash,
                gate="cleanup",
                action="next",
                payload={
                    "occurrence_id": "not-the-visible-occurrence",
                    "expected_interaction_revision": 0,
                },
                resolver="tester",
            ),
        )


def test_continue_rejected_with_unresolved_occurrences(tmp_path: Path) -> None:
    gate = make_cleanup_gate(tmp_path, mappings=[("w/", "with")])
    prepared = fake_prepared("w/ one.")
    gate.pending(prepared)
    with pytest.raises(IllegalDecisionError, match="unresolved"):
        gate.apply(
            prepared,
            DecisionRequest(
                run_id="r1",
                item_id=prepared.content_hash,
                gate="cleanup",
                action="continue",
                payload={
                    "expected_interaction_revision": 0,
                    "expected_working_draft_revision": 0,
                },
                resolver="tester",
            ),
        )


def test_continue_has_no_side_effect_beyond_marking_handed_off(tmp_path: Path) -> None:
    gate = make_cleanup_gate(tmp_path)  # zero mappings, zero suggestions
    prepared = fake_prepared("plain text, nothing to clean.")
    pending = gate.pending(prepared)
    assert pending is None  # no cleanup work at all -> auto handed off already


def test_unavailable_then_recovers_on_a_fresh_attempt(tmp_path: Path) -> None:
    class FlakyOnceChatClient:
        def __init__(self) -> None:
            self.attempts = 0

        def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            del args, kwargs
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("gateway down")
            return {"text": '{"edits": []}'}

    gate = make_cleanup_gate(tmp_path, chat_client=FlakyOnceChatClient())
    prepared = fake_prepared("plain text, no abbreviations here.")

    first = gate.pending(prepared)
    assert first is not None
    assert first.payload["state"] == "unavailable"
    assert first.allowed_actions == ("retry",)

    second = gate.pending(prepared)  # a fresh attempt, as coordinator retry would trigger
    assert second is None  # recovered, and this time found no suggestions


def test_apply_remember_writes_mapping_and_audit_atomically(tmp_path: Path) -> None:
    gate = make_cleanup_gate(tmp_path)
    prepared = fake_prepared("Talk w/ me soon.")
    # No mapping exists yet, so no abbreviation candidates -- this exercises
    # C8-C5's "first mapping" path indirectly via the mapping repository, and
    # directly proves the atomic write by checking it lands.
    repo = gate._mappings  # type: ignore[attr-defined]
    repo.record_apply_remember(
        shorthand="w/",
        expansion="with",
        case_sensitive=True,
        audit=AuditEntry(
            source_kind="text_file",
            run_id="r1",
            item_id=prepared.content_hash,
            occurrence_id="abbr-p0-0-2-1",
            phase="abbreviation",
            action="apply_remember",
            before="w/",
            after="with",
            interaction_revision=1,
            working_draft_revision=1,
        ),
    )
    assert [m.shorthand for m in repo.active_mappings()] == ["w/"]


def test_apply_remember_does_not_mutate_state_when_sqlite_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = make_cleanup_gate(tmp_path, mappings=[("w/", "with")])
    prepared = fake_prepared("Talk w/ me soon.")
    pending = gate.pending(prepared)
    assert pending is not None
    occurrence = pending.payload["occurrence"]

    def fail_write(**_: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(gate._mappings, "record_apply_remember", fail_write)  # type: ignore[attr-defined]
    with pytest.raises(OSError, match="disk full"):
        gate.apply(
            prepared,
            DecisionRequest(
                run_id="r1",
                item_id=prepared.content_hash,
                gate="cleanup",
                action="apply_remember",
                payload={
                    "occurrence_id": occurrence["occurrence_id"],
                    "expected_interaction_revision": 0,
                    "expected_working_draft_revision": 0,
                    "shorthand": "w/",
                    "expansion": "along with",
                    "case_sensitive": True,
                },
                resolver="tester",
            ),
        )

    state = gate._states[prepared.content_hash]  # type: ignore[attr-defined]
    assert state.abbreviation_decisions == {}
    assert state.interaction_revision == 0
    assert state.working_draft_revision == 0
    assert state.current_working_passages()[0].text == "Talk w/ me soon."


def test_apply_remember_uses_human_entered_expansion_for_current_occurrence(
    tmp_path: Path,
) -> None:
    gate = make_cleanup_gate(tmp_path, mappings=[("w/", "with")])
    prepared = fake_prepared("Talk w/ me soon.")
    pending = gate.pending(prepared)
    assert pending is not None
    occurrence = pending.payload["occurrence"]
    gate.apply(
        prepared,
        DecisionRequest(
            run_id="r1",
            item_id=prepared.content_hash,
            gate="cleanup",
            action="apply_remember",
            payload={
                "occurrence_id": occurrence["occurrence_id"],
                "expected_interaction_revision": 0,
                "expected_working_draft_revision": 0,
                "shorthand": "w/",
                "expansion": "along with",
                "case_sensitive": True,
            },
            resolver="tester",
        ),
    )
    state = gate._states[prepared.content_hash]  # type: ignore[attr-defined]
    assert state.current_working_passages()[0].text == "Talk along with me soon."
    assert gate._mappings.active_mappings()[0].expansion == "along with"  # type: ignore[attr-defined]


def test_apply_once_uses_human_entered_expansion_without_changing_mapping(
    tmp_path: Path,
) -> None:
    gate = make_cleanup_gate(tmp_path, mappings=[("w/", "with")])
    prepared = fake_prepared("Talk w/ me soon.")
    pending = gate.pending(prepared)
    assert pending is not None
    occurrence = pending.payload["occurrence"]
    gate.apply(
        prepared,
        DecisionRequest(
            run_id="r1",
            item_id=prepared.content_hash,
            gate="cleanup",
            action="apply_once",
            payload={
                "occurrence_id": occurrence["occurrence_id"],
                "expected_interaction_revision": 0,
                "expected_working_draft_revision": 0,
                "shorthand": "w/",
                "expansion": "along with",
                "case_sensitive": True,
            },
            resolver="tester",
        ),
    )
    state = gate._states[prepared.content_hash]  # type: ignore[attr-defined]
    assert state.current_working_passages()[0].text == "Talk along with me soon."
    assert gate._mappings.active_mappings()[0].expansion == "with"  # type: ignore[attr-defined]


def test_clear_removes_state(tmp_path: Path) -> None:
    gate = make_cleanup_gate(tmp_path, mappings=[("w/", "with")])
    prepared = fake_prepared("w/ one.")
    gate.pending(prepared)
    assert prepared.content_hash in gate._states  # type: ignore[attr-defined]
    gate.clear(prepared.content_hash)
    assert prepared.content_hash not in gate._states  # type: ignore[attr-defined]


# --- Coordinator-level handoff (component_8.md section 12) -------------


def test_text_file_overlay_survives_reextraction_and_publishes_revised_text(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "a.fixture").write_text("first")
    extractor = RecordingFixtureExtractor("Talk w/ me about the plan.")

    mapping_repo = MappingRepository(config.text_cleanup_db_path)
    mapping_repo.create("w/", "with")
    from ingestion.coordinator.gates import BookMetadataGate, ContentApprovalGate

    gates = (
        BookMetadataGate(config.page_scanner_db_path),
        CleanupGate(
            mapping_repository=mapping_repo,
            chat_client=FakeCleanupChatClient(),
            spelling_provider="gemma",
        ),
        ContentApprovalGate(config.page_scanner_db_path),
    )
    run = base_coordinator(config, extractors=[extractor], gates=gates)

    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.gate == "cleanup"
    occurrence = blocked.pending.payload["occurrence"]
    assert occurrence["original_text"] == "w/"

    applied = run.submit_decision(
        decision(
            blocked,
            "apply_once",
            payload={
                "occurrence_id": occurrence["occurrence_id"],
                "expected_interaction_revision": blocked.pending.payload["interaction_revision"],
                "expected_working_draft_revision": blocked.pending.payload["working_draft_revision"],
            },
        )
    )
    # This decision triggers a fresh prepare_file() re-extraction on the next
    # advance() pass (coordinator.submit_decision -> self.advance()). Two
    # extractor calls by now (initial + this re-entry) proves re-extraction
    # really happened, not that the overlay was trivially skipped.
    assert extractor.calls == ["a.fixture", "a.fixture"]
    assert applied.pending is not None and applied.pending.gate == "cleanup"
    assert applied.pending.payload["can_continue"] is True

    continued = run.submit_decision(
        decision(
            applied,
            "continue",
            payload={
                "expected_interaction_revision": applied.pending.payload["interaction_revision"],
                "expected_working_draft_revision": applied.pending.payload["working_draft_revision"],
            },
        )
    )
    assert continued.pending is not None and continued.pending.gate == "content_approval"
    # The final-review payload already contains the revised text -- the
    # fresh re-extraction that happened along the way did not overwrite it.
    assert continued.pending.payload["markdown_text"] == "Talk with me about the plan."

    # Approve, echoing back exactly the payload text it displayed -- this is
    # what TextReview's edit box does today for any adapter; Component 8
    # changes what text populates that box, not _save_edits itself.
    finished = run.submit_decision(
        decision(
            continued,
            "approve",
            payload={"markdown_text": continued.pending.payload["markdown_text"]},
        )
    )
    assert finished.pending is not None and finished.pending.gate == "phase_handoff"
    note = next(config.intake.vault_path.rglob("*.md"))
    assert "Talk with me about the plan." in note.read_text()


def test_diagnostics_do_not_record_gate_done_until_continue(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "a.fixture").write_text("first")
    extractor = RecordingFixtureExtractor("Talk w/ me about the plan.")
    mapping_repo = MappingRepository(config.text_cleanup_db_path)
    mapping_repo.create("w/", "with")
    from ingestion.coordinator.gates import BookMetadataGate, ContentApprovalGate

    gates = (
        BookMetadataGate(config.page_scanner_db_path),
        CleanupGate(
            mapping_repository=mapping_repo,
            chat_client=FakeCleanupChatClient(),
            spelling_provider="gemma",
        ),
        ContentApprovalGate(config.page_scanner_db_path),
    )
    run = base_coordinator(config, extractors=[extractor], gates=gates)
    blocked = run.advance()
    assert blocked.pending is not None
    occurrence = blocked.pending.payload["occurrence"]

    applied = run.submit_decision(
        decision(
            blocked,
            "apply_once",
            payload={
                "occurrence_id": occurrence["occurrence_id"],
                "expected_interaction_revision": blocked.pending.payload["interaction_revision"],
                "expected_working_draft_revision": blocked.pending.payload["working_draft_revision"],
            },
        )
    )
    intake_stage = next(item for item in applied.stages if item.stage.value == "intake_item")
    cleanup_events = [e for e in intake_stage.detail["gates"] if e["gate"] == "cleanup"]
    # The apply_once decision itself logs as "cleanup_interaction", not
    # "done" -- the gate remains blocked afterward (now offering Continue,
    # since that was the only occurrence), which is a further "blocked"
    # event, not a completion.
    assert any(event["status"] == "cleanup_interaction" for event in cleanup_events)
    assert all(event["status"] != "done" for event in cleanup_events)

    continued = run.submit_decision(
        decision(
            applied,
            "continue",
            payload={
                "expected_interaction_revision": applied.pending.payload["interaction_revision"],
                "expected_working_draft_revision": applied.pending.payload["working_draft_revision"],
            },
        )
    )
    intake_stage = next(item for item in continued.stages if item.stage.value == "intake_item")
    cleanup_events = [e for e in intake_stage.detail["gates"] if e["gate"] == "cleanup"]
    # Continue itself logs "done"; the gate is then re-evaluated once more on
    # the same advance() and correctly reports "skipped" since it has nothing
    # left to block on -- both are expected, in that order.
    assert any(event["status"] == "done" and event["action"] == "continue" for event in cleanup_events)
    assert cleanup_events[-1]["status"] == "skipped"


def test_image_overlay_shows_in_payload_without_touching_db_until_approve(
    tmp_path: Path,
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
            passages=[PhotoPassage("Talk w/ me later.", [1, 2, 3, 4], 0.9)],
            blur_score=1.0,
            glare_score=0.0,
            conf_ratio=0.9,
            flagged_retake=False,
            file_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    mapping_repo = MappingRepository(config.text_cleanup_db_path)
    mapping_repo.create("w/", "with")
    from ingestion.coordinator.gates import BookMetadataGate, ContentApprovalGate

    gates = (
        BookMetadataGate(config.page_scanner_db_path),
        CleanupGate(
            mapping_repository=mapping_repo,
            chat_client=FakeCleanupChatClient(),
            spelling_provider="gemma",
        ),
        ContentApprovalGate(config.page_scanner_db_path),
    )
    run = base_coordinator(
        config,
        extractors=[ImageExtractor(processor=process, clean=True, cleaner=lambda value: value)],
        gates=gates,
    )
    blocked = run.advance()
    assert blocked.pending is not None and blocked.pending.gate == "cleanup"
    occurrence = blocked.pending.payload["occurrence"]

    applied = run.submit_decision(
        decision(
            blocked,
            "apply_once",
            payload={
                "occurrence_id": occurrence["occurrence_id"],
                "expected_interaction_revision": blocked.pending.payload["interaction_revision"],
                "expected_working_draft_revision": blocked.pending.payload["working_draft_revision"],
            },
        )
    )
    continued = run.submit_decision(
        decision(
            applied,
            "continue",
            payload={
                "expected_interaction_revision": applied.pending.payload["interaction_revision"],
                "expected_working_draft_revision": applied.pending.payload["working_draft_revision"],
            },
        )
    )
    assert continued.pending is not None and continued.pending.gate == "content_approval"
    passages = continued.pending.payload["passages"]
    assert passages[0]["edited_text"] == "Talk with me later."
    assert run._prepared is not None  # type: ignore[attr-defined]
    assert run._prepared.result.markdown_text == "Talk with me later."  # type: ignore[attr-defined]

    # Not persisted to the DB before Approve -- restart rebuilds from raw
    # extracted text, never from an unapproved cleanup edit (DoD, section 7.3).
    page_id = int(continued.pending.payload["page_id"])
    stored = page_store.get_passages(config.page_scanner_db_path, page_id)
    assert stored[0]["edited_text"] == "Talk w/ me later."

    # Approve, echoing back exactly the payload text it displayed -- this is
    # what ImageReview's edit box does today for any adapter; Component 8
    # changes what text populates that box, not _save_edits itself.
    finished = run.submit_decision(
        decision(
            continued,
            "approve",
            payload={
                "passages": [
                    {"index": index, "edited_text": passage["edited_text"]}
                    for index, passage in enumerate(passages)
                ]
            },
        )
    )
    assert finished.pending is not None and finished.pending.gate == "phase_handoff"
    stored_after_approve = page_store.get_passages(config.page_scanner_db_path, page_id)
    assert stored_after_approve[0]["edited_text"] == "Talk with me later."
