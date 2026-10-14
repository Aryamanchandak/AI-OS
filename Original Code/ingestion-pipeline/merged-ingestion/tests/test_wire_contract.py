"""Every pending the coordinator can emit must satisfy the typed wire contract.

`GET /api/ingestion/run` declares `response_model=RunSnapshotBody`, so FastAPI
validates the coordinator's `PendingDecision` on the way out. A pending whose
payload does not match its adapter's model is not a cosmetic mismatch -- it is a
500 on every poll for as long as that pending is current, which makes the run
un-renderable and any action it offers unreachable.

The rest of the suite asserts on the in-process `RunView` and therefore cannot
see that class of defect at all. These tests close that gap by pushing real
coordinator-produced pendings through the same model FastAPI uses.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from cockpit.server import PendingBody, ReviewService, create_router
from ingestion.config import IngestionConfig
from ingestion.coordinator.coordinator import RunCoordinator
from ingestion.coordinator.errors import GateUnavailable
from ingestion.coordinator.report import read_report
from ingestion.coordinator.stages import RunStage
from ingestion.coordinator.state import PendingDecision
from ingestion.intake.base import IntakeResult
from ingestion.intake.extractors.image import ImageExtractor
from ingestion.sources.page_scanner.photo_pipeline import Passage, PhotoResult
from ingestion.text_cleanup.store import MappingRepository

from tests.test_coordinator import (
    ProposalPipeline,
    ProposalStore,
    coordinator,
    decision,
    empty_capture,
    make_config,
    ok_preflight,
)
from tests.test_cockpit_server import wait_until_idle

_PENDING: TypeAdapter[Any] = TypeAdapter(PendingBody)


def assert_on_the_wire(pending: PendingDecision | None) -> None:
    """Validate one pending exactly as FastAPI's response model does."""

    if pending is None:
        return
    try:
        _PENDING.validate_python(
            {
                "item_id": pending.item_id,
                "item_type": pending.item_type,
                "gate": pending.gate,
                "adapter": pending.adapter,
                "payload": pending.payload,
                "allowed_actions": list(pending.allowed_actions),
                "blocking_reason": pending.blocking_reason,
            }
        )
    except ValidationError as error:
        raise AssertionError(
            f"pending adapter={pending.adapter!r} gate={pending.gate!r} cannot be "
            f"serialized by RunSnapshotBody:\n{error}\npayload={pending.payload!r}"
        ) from error


def _cleanup_payload(pending: PendingDecision) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "expected_interaction_revision": pending.payload["interaction_revision"],
        "expected_working_draft_revision": pending.payload["working_draft_revision"],
    }
    occurrence = pending.payload.get("occurrence")
    if isinstance(occurrence, dict):
        payload["occurrence_id"] = occurrence["occurrence_id"]
    return payload


def drive(run: RunCoordinator, view: Any, *, limit: int = 16) -> list[str]:
    """Take the first legal action at every stop, validating each pending."""

    adapters: list[str] = []
    for _ in range(limit):
        pending = view.pending
        if pending is None:
            break
        assert_on_the_wire(pending)
        adapters.append(pending.adapter)
        payload: dict[str, Any] = {}
        if pending.adapter == "cleanup":
            payload = _cleanup_payload(pending)
        elif pending.adapter == "text_file":
            payload = {"markdown_text": pending.payload["markdown_text"]}
        view = run.submit_decision(decision(view, pending.allowed_actions[0], payload=payload))
    return adapters


def test_markdown_flow_pendings_are_serializable(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "note.md").write_text(
        "# Note\n\nTalk w/ me about the plan.", encoding="utf-8"
    )
    MappingRepository(config.text_cleanup_db_path).create("w/", "with")

    run = coordinator(config)
    try:
        adapters = drive(run, run.advance())
    finally:
        run.close()
    assert "cleanup" in adapters and "text_file" in adapters, adapters


def test_image_flow_pendings_are_serializable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    book = config.intake.drop_folder / "atomic-habits"
    book.mkdir()
    (book / "page.jpg").write_bytes(b"photo")
    (book / ".book.json").write_text(
        json.dumps({"title": "Atomic Habits", "confidence": "fuzzy"})
    )
    MappingRepository(config.text_cleanup_db_path).create("w/", "with")

    def process(path: Path, *, hsv_params: object) -> PhotoResult:
        del hsv_params
        return PhotoResult(
            passages=[Passage("Talk w/ me about habits.", [1, 2, 3, 4], 0.9)],
            blur_score=1.0,
            glare_score=0.0,
            conf_ratio=0.9,
            flagged_retake=False,
            file_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    monkeypatch.setattr(
        "ingestion.coordinator.coordinator.append_book_highlight_passages",
        lambda vault, result: vault / "highlights.md",
    )

    def write_note(vault: Path, result: IntakeResult) -> Path:
        del result
        note = vault / "page.md"
        note.write_text("approved", encoding="utf-8")
        return note

    run = coordinator(
        config,
        extractors=[
            ImageExtractor(processor=process, clean=True, cleaner=lambda value: value)
        ],
        vault_writer=write_note,
    )
    try:
        adapters = drive(run, run.advance())
    finally:
        run.close()
    assert {"book_identity", "cleanup", "image_ocr"} <= set(adapters), adapters


def _proposal_run(config: IngestionConfig, pipeline: Any) -> RunCoordinator:
    @contextmanager
    def session(_config: IngestionConfig) -> Iterator[Any]:
        yield SimpleNamespace(pipeline=pipeline)

    return RunCoordinator(
        config,
        resolver="tester",
        preflight_runner=ok_preflight,
        session_factory=session,
        capture_function=empty_capture,
    )


def test_proposal_level_pending_is_serializable(tmp_path: Path) -> None:
    run = _proposal_run(make_config(tmp_path), ProposalPipeline())
    try:
        blocked = run.advance()
        assert blocked.pending is not None and blocked.pending.item_type == "proposal"
        assert_on_the_wire(blocked.pending)
    finally:
        run.close()


def test_envelope_level_pending_is_serializable(tmp_path: Path) -> None:
    """An envelope with no still-pending items takes the other payload arm."""

    class SettledItemsStore(ProposalStore):
        def pending_reviews(self) -> list[dict[str, Any]]:
            reviews = super().pending_reviews()
            for review in reviews:
                for item in review["items"]:
                    item["status"] = "approved"
            return reviews

    pipeline = ProposalPipeline()
    pipeline.store = SettledItemsStore()
    run = _proposal_run(make_config(tmp_path), pipeline)
    try:
        blocked = run.advance()
        assert blocked.pending is not None and blocked.pending.item_type == "envelope"
        assert_on_the_wire(blocked.pending)
    finally:
        run.close()


def test_gate_unavailable_never_parks_an_unserializable_pending(
    tmp_path: Path,
) -> None:
    """component_8.md section 7.4 item 6: "Do not rely on the coordinator's
    current generic ``GateUnavailable`` payload (``{"error": ...}``), because
    that shape cannot satisfy the typed cleanup contract." No member of the
    pending union can hold a bare error, so this path must fail the run rather
    than park a pending that ``GET /run`` cannot serialize."""

    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "note.md").write_text("body", encoding="utf-8")

    class Unavailable:
        name = "cleanup"

        def pending(self, prepared: object) -> None:
            del prepared
            raise GateUnavailable("checker down")

        def apply(self, prepared: object, request: object) -> None:
            del prepared, request

    run = coordinator(config, gates=[Unavailable()])
    try:
        failed = run.advance()
        assert failed.stage == RunStage.FAILED
        assert failed.last_error is not None and failed.last_error.retryable
        # Whatever is on the wire has to be serializable, pending or not.
        assert_on_the_wire(failed.pending)
    finally:
        run.close()


def test_retry_after_an_intake_failure_can_finish_the_run(tmp_path: Path) -> None:
    """T60: "You start Ollama, call ``retry()``, and it picks up the same
    photo." ``_fail()`` counts an INTAKE_ITEM failure as a failed intake item,
    and INTAKE_BARRIER refuses to pass while that count is non-zero -- so
    without rolling it back, a retry failed a second time even after the
    retried item succeeded."""

    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "note.md").write_text(
        "# Note\n\nEnough text.", encoding="utf-8"
    )

    class FailsOnce:
        name = "cleanup"

        def __init__(self) -> None:
            self.raised = False

        def pending(self, prepared: object) -> None:
            del prepared
            if not self.raised:
                self.raised = True
                raise GateUnavailable("checker down")
            return None

        def apply(self, prepared: object, request: object) -> None:
            del prepared, request

    run = coordinator(config, gates=[FailsOnce()])
    try:
        assert run.advance().stage == RunStage.FAILED
        resumed = run.retry()
        assert resumed.stage != RunStage.FAILED, resumed.last_error
        assert resumed.pending is not None
        assert resumed.pending.gate == "phase_handoff"
        assert_on_the_wire(resumed.pending)
        assert resumed.pending.payload["failed"] == 0
        # Finishing the recovered run must still release the lock the failure
        # dropped and `retry()` took back.
        finished = run.submit_decision(decision(resumed, "stop"))
        assert finished.terminal_result == "complete"
    finally:
        run.close()
    assert not config.coordinator_db_path.with_suffix(".lock").exists()


def test_repeated_retries_keep_the_intake_failure_count_stable(
    tmp_path: Path,
) -> None:
    """The rollback has to survive more than one round trip: fail, retry, fail
    on the same item again, retry again, succeed."""

    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "note.md").write_text(
        "# Note\n\nEnough text.", encoding="utf-8"
    )

    class FailsTwice:
        name = "cleanup"

        def __init__(self) -> None:
            self.raised = 0

        def pending(self, prepared: object) -> None:
            del prepared
            if self.raised < 2:
                self.raised += 1
                raise GateUnavailable(f"checker down ({self.raised})")
            return None

        def apply(self, prepared: object, request: object) -> None:
            del prepared, request

    gate = FailsTwice()
    run = coordinator(config, gates=[gate])
    try:
        assert run.advance().stage == RunStage.FAILED
        second = run.retry()
        assert second.stage == RunStage.FAILED, "the item was expected to fail again"
        assert second.last_error is not None
        assert "checker down (2)" in second.last_error.message
        third = run.retry()
        assert third.stage != RunStage.FAILED, third.last_error
        assert third.pending is not None and third.pending.gate == "phase_handoff"
        assert third.pending.payload["failed"] == 0
        assert gate.raised == 2
    finally:
        run.close()


# --- The same walk, through the real HTTP surface ---------------------------


class _RealCoordinatorAPI:
    """A `CoordinatorAPI` backed by a real `RunCoordinator`.

    `tests/test_cockpit_server.py` drives the router with a `FakeCoordinator`
    returning a hand-built `RunView`, and its union test validates hand-written
    fixture payloads -- so nothing today puts a *coordinator-produced* payload
    through `_jsonable()` and the response model together. That composition is
    what the shell actually receives.
    """

    def __init__(self, run: RunCoordinator) -> None:
        self.run = run

    def start_run(self, config: IngestionConfig, *, resolver: str) -> Any:
        del config, resolver
        return self.run.advance()

    def submit_decision(self, config: IngestionConfig, request: Any) -> Any:
        del config
        return self.run.submit_decision(request)

    def retry(self, config: IngestionConfig) -> Any:
        del config
        return self.run.retry()

    def run_report(self, config: IngestionConfig, run_id: str | None = None) -> Any:
        del config
        return read_report(self.run.config.database_root / "reports", run_id)


def test_full_run_is_serializable_over_http(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.intake is not None
    (config.intake.drop_folder / "note.md").write_text(
        "# Note\n\nTalk w/ me about the plan.", encoding="utf-8"
    )
    MappingRepository(config.text_cleanup_db_path).create("w/", "with")

    run = coordinator(config)
    service = ReviewService(
        config, resolver="reviewer", coordinator_api=_RealCoordinatorAPI(run)
    )
    app = FastAPI()
    app.include_router(create_router(service), prefix="/api/ingestion")

    adapters: list[str] = []
    try:
        with TestClient(app) as client:
            assert client.post("/api/ingestion/run/start").status_code == 202
            state = wait_until_idle(client)
            for _ in range(16):
                pending = state["view"]["pending"]
                if pending is None:
                    break
                adapters.append(pending["adapter"])
                payload: dict[str, Any] = {}
                if pending["adapter"] == "cleanup":
                    payload = {
                        "expected_interaction_revision": pending["payload"][
                            "interaction_revision"
                        ],
                        "expected_working_draft_revision": pending["payload"][
                            "working_draft_revision"
                        ],
                    }
                    occurrence = pending["payload"].get("occurrence")
                    if occurrence is not None:
                        payload["occurrence_id"] = occurrence["occurrence_id"]
                elif pending["adapter"] == "text_file":
                    payload = {"markdown_text": pending["payload"]["markdown_text"]}
                response = client.post(
                    "/api/ingestion/run/decision",
                    json={
                        "run_id": state["view"]["run_id"],
                        "item_id": pending["item_id"],
                        "gate": pending["gate"],
                        "action": pending["allowed_actions"][0],
                        "payload": payload,
                        "resolver": "reviewer",
                        "expected_revision": state["operation"]["revision"],
                    },
                )
                assert response.status_code == 202, response.text
                state = wait_until_idle(client)
                assert state["operation"]["error"] is None, state["operation"]
    finally:
        service.close()
        run.close()
    assert "cleanup" in adapters and "text_file" in adapters, adapters
