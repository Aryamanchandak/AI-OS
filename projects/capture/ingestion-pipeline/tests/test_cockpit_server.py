from __future__ import annotations

from pathlib import Path
from threading import Event
import time
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from cockpit.server import PendingBody, ReviewService, create_router
from ingestion.config import IngestionConfig, IntakeConfig
from ingestion.coordinator.report import RunReportView
from ingestion.coordinator.stages import RunStage, StageStatus
from ingestion.sources.page_scanner import store as page_scanner_store
from ingestion.coordinator.state import (
    DecisionRequest,
    PendingDecision,
    ProgressView,
    RunView,
    StageView,
)


def make_config(tmp_path: Path) -> IngestionConfig:
    drop = tmp_path / "drop"
    vault = tmp_path / "vault"
    drop.mkdir()
    vault.mkdir()
    return IngestionConfig(
        database_root=tmp_path / "Database",
        intake=IntakeConfig(drop_folder=drop, vault_path=vault),
    )


def run_view(photo: Path, *, adapter: str = "image_ocr") -> RunView:
    pending = PendingDecision(
        item_id="image-hash",
        item_type="image",
        gate="content_approval",
        adapter=adapter,
        payload={
            "photo_path": str(photo),
            "passages": [
                {
                    "index": 0,
                    "ocr_text": "Original",
                    "edited_text": "Original",
                    "bbox": [1, 2, 3, 4],
                }
            ],
        },
        allowed_actions=("approve", "discard", "retake"),
        blocking_reason="approval required",
    )
    return RunView(
        run_id="run-1",
        stage=RunStage.INTAKE_ITEM,
        stage_status=StageStatus.BLOCKED,
        stages=(StageView(RunStage.INTAKE_ITEM, StageStatus.BLOCKED, {}),),
        pending=pending,
        progress=ProgressView(intake_total=1),
        last_error=None,
        terminal_result=None,
    )


class FakeCoordinator:
    def __init__(self, view: RunView) -> None:
        self.view = view
        self.decisions: list[DecisionRequest] = []
        self.decision_started = Event()
        self.release_decision = Event()
        self.block_decisions = False
        self.fail_with: str | None = None

    def _answer(self) -> RunView:
        if self.fail_with is not None:
            raise RuntimeError(self.fail_with)
        return self.view

    def start_run(self, config: IngestionConfig, *, resolver: str) -> RunView:
        del config
        assert resolver == "reviewer"
        return self._answer()

    def submit_decision(
        self, config: IngestionConfig, decision: DecisionRequest
    ) -> RunView:
        del config
        self.decisions.append(decision)
        self.decision_started.set()
        if self.block_decisions:
            assert self.release_decision.wait(timeout=3)
        return self._answer()

    def retry(self, config: IngestionConfig) -> RunView:
        del config
        return self._answer()

    def run_report(
        self, config: IngestionConfig, run_id: str | None = None
    ) -> RunReportView:
        del config
        resolved = str(run_id or "run-1")
        return RunReportView(
            run_id=resolved,
            path=Path("/reports") / f"{resolved}.json",
            data={"run_id": resolved, "terminal_result": "complete"},
        )


def wait_until_idle(client: TestClient) -> dict[str, Any]:
    for _ in range(100):
        state = client.get("/api/ingestion/run").json()
        if state["operation"]["state"] != "submitting":
            return state
        time.sleep(0.01)
    raise AssertionError("service did not become idle")


def decision_body() -> dict[str, Any]:
    return {
        "run_id": "run-1",
        "item_id": "image-hash",
        "gate": "content_approval",
        "action": "approve",
        "payload": {
            "passages": [{"index": 0, "edited_text": "Corrected"}],
            "page_number": 42,
        },
    }


def mounted_service(
    tmp_path: Path, fake: FakeCoordinator
) -> tuple[FastAPI, ReviewService]:
    service = ReviewService(
        make_config(tmp_path), resolver="reviewer", coordinator_api=fake
    )
    app = FastAPI()
    app.include_router(create_router(service), prefix="/api/ingestion")
    return app, service


def test_every_adapter_payload_validates_through_the_discriminated_union() -> None:
    base = {
        "item_id": "item-1",
        "item_type": "fixture",
        "gate": "fixture",
        "allowed_actions": ["approve"],
        "blocking_reason": "review required",
    }
    payloads = [
        {
            **base,
            "adapter": "book_identity",
            "payload": {
                "proposed_title": "A Book",
                "proposed_author": "An Author",
                "proposed_year": 2026,
                "confidence": "exact",
                "meta_source": "fixture",
                "photo_count": 2,
                "resolved_slug": "a-book",
                "future_field": "allowed",
            },
        },
        {
            **base,
            "adapter": "image_ocr",
            "payload": {
                "photo_path": "/tmp/page.jpg",
                "page_number": 4,
                "passages": [
                    {
                        "index": 0,
                        "ocr_text": "Original",
                        "edited_text": "Edited",
                        "bbox": [1, 2, 3, 4],
                    }
                ],
                "conf_ratio": 0.1,
                "blur_score": 2.0,
                "glare_score": 0.0,
            },
        },
        {
            **base,
            "adapter": "text_file",
            "payload": {
                "source_path": "/tmp/note.md",
                "title": "Note",
                "extraction_method": "markdown",
                "warnings": [],
                "markdown_text": "Draft",
            },
        },
        {
            **base,
            "item_id": "",
            "adapter": "phase_handoff",
            "payload": {
                "discovered": 3,
                "published": 2,
                "discarded": 1,
                "retake": 0,
                "duplicate": 0,
                "failed": 0,
                "note_paths": ["Note.md"],
            },
        },
        {
            **base,
            "adapter": "knowledge_proposal",
            "payload": {
                "envelope_level": True,
                "review_signals": [],
                "source_record_id": "source-1",
                "highlight_index": 0,
                "highlight_text": "Evidence",
                "model_confidence": 0.8,
            },
        },
        {
            **base,
            "adapter": "knowledge_proposal",
            "payload": {
                "envelope_id": "envelope-1",
                "proposal_id": "proposal-1",
                "proposal_type": "concept",
                "proposal": {"label": "Duration"},
                "source_note_path": "Bonds.md",
                "origin_kind": "page_scanner",
                "highlight_index": 0,
                "highlight_text": "Duration",
                "evidence_quote": "Duration",
                "evidence_start_char": 0,
                "evidence_end_char": 8,
                "proposal_confidence": 0.91,
                "envelope_confidence": 0.99,
                "signals": [],
                "sibling_proposals": [],
            },
        },
    ]

    adapter = TypeAdapter(PendingBody)
    validated = [adapter.validate_python(value) for value in payloads]

    assert [value.adapter for value in validated] == [
        "book_identity",
        "image_ocr",
        "text_file",
        "phase_handoff",
        "knowledge_proposal",
        "knowledge_proposal",
    ]
    assert validated[0].payload.model_extra == {"future_field": "allowed"}
    assert validated[3].item_id == ""


def test_start_serializes_and_exposes_json_run_view(tmp_path: Path) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"photo")
    fake = FakeCoordinator(run_view(photo))
    app, service = mounted_service(tmp_path, fake)

    try:
        with TestClient(app) as client:
            assert client.post("/api/ingestion/run/start").status_code == 202
            state = wait_until_idle(client)
    finally:
        service.close()

    assert state["view"]["run_id"] == "run-1"
    assert state["view"]["stage"] == "intake_item"
    assert state["view"]["pending"]["adapter"] == "image_ocr"
    assert state["reviewer"] == "reviewer"
    assert state["contract_version"] == "component6.v1"


def test_decision_is_forwarded_exactly_and_duplicate_is_refused(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"photo")
    fake = FakeCoordinator(run_view(photo))
    app, service = mounted_service(tmp_path, fake)

    try:
        with TestClient(app) as client:
            client.post("/api/ingestion/run/start")
            wait_until_idle(client)
            fake.block_decisions = True
            first = client.post("/api/ingestion/run/decision", json=decision_body())
            assert first.status_code == 202
            assert fake.decision_started.wait(timeout=1)
            duplicate = client.post(
                "/api/ingestion/run/decision", json=decision_body()
            )
            assert duplicate.status_code == 409
            fake.release_decision.set()
            wait_until_idle(client)
    finally:
        service.close()

    assert len(fake.decisions) == 1
    saved = fake.decisions[0]
    assert saved.resolver == "reviewer"
    assert saved.payload["page_number"] == 42
    assert saved.payload["passages"][0]["edited_text"] == "Corrected"


def test_router_mounts_under_the_unified_ingestion_prefix_and_rejects_stale_revision(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"photo")
    fake = FakeCoordinator(run_view(photo))
    service = ReviewService(make_config(tmp_path), resolver="reviewer", coordinator_api=fake)
    app = FastAPI()
    app.include_router(create_router(service), prefix="/api/ingestion")

    try:
        with TestClient(app) as client:
            assert client.post("/api/ingestion/run/start").status_code == 202
            state = None
            for _ in range(100):
                state = client.get("/api/ingestion/run").json()
                if state["operation"]["state"] != "submitting":
                    break
                time.sleep(0.01)
            assert state is not None
            assert state["operation"]["revision"] == 1

            body = decision_body()
            body["expected_revision"] = 0
            stale = client.post("/api/ingestion/run/decision", json=body)
            assert stale.status_code == 412
            assert "current revision is 1" in stale.json()["detail"]
    finally:
        service.close()


def test_evidence_endpoint_only_serves_the_current_pending_item(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"current-photo")
    fake = FakeCoordinator(run_view(photo))
    app, service = mounted_service(tmp_path, fake)

    try:
        with TestClient(app) as client:
            client.post("/api/ingestion/run/start")
            wait_until_idle(client)
            current = client.get("/api/ingestion/evidence/run-1/image-hash")
            wrong_run = client.get("/api/ingestion/evidence/wrong/image-hash")
            wrong_item = client.get("/api/ingestion/evidence/run-1/wrong")
    finally:
        service.close()

    assert current.status_code == 200
    assert current.content == b"current-photo"
    assert current.headers["cache-control"] == "no-store"
    assert wrong_run.status_code == 404
    assert wrong_item.status_code == 404


def knowledge_proposal_run_view(*, photo_page_id: int | None) -> RunView:
    pending = PendingDecision(
        item_id="concept-1",
        item_type="proposal",
        gate="proposal",
        adapter="knowledge_proposal",
        payload={
            "envelope_id": "envelope-1",
            "proposal_id": "concept-1",
            "proposal_type": "concept",
            "proposal": {"proposal_id": "concept-1", "label": "Duration"},
            "source_note_path": "Page Scanners/book/book-highlights.md",
            "origin_kind": "page_scanner",
            "highlight_index": 0,
            "highlight_text": "Duration",
            "evidence_quote": "Duration",
            "evidence_start_char": 0,
            "evidence_end_char": 8,
            "proposal_confidence": 0.91,
            "envelope_confidence": 0.99,
            "signals": [],
            "sibling_proposals": [],
            "photo_page_id": photo_page_id,
            "photo_page_number": 9,
            "photo_passages": [],
        },
        allowed_actions=("approve", "edit", "reject"),
        blocking_reason="semantic proposal requires review",
    )
    return RunView(
        run_id="run-1",
        stage=RunStage.PROPOSAL_REVIEW,
        stage_status=StageStatus.BLOCKED,
        stages=(StageView(RunStage.PROPOSAL_REVIEW, StageStatus.BLOCKED, {}),),
        pending=pending,
        progress=ProgressView(intake_total=1),
        last_error=None,
        terminal_result=None,
    )


def test_evidence_endpoint_serves_the_photo_behind_a_knowledge_proposal(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "page-9.jpg"
    photo.write_bytes(b"page-nine-bytes")
    config = make_config(tmp_path)
    page_scanner_store.init_db(config.page_scanner_db_path)
    page_id = page_scanner_store.insert_page(
        config.page_scanner_db_path,
        batch="batch-1",
        author=None,
        image_path=str(photo),
        file_hash="hash-1",
        page_number=9,
    )
    assert page_id is not None
    fake = FakeCoordinator(knowledge_proposal_run_view(photo_page_id=page_id))
    app = FastAPI()
    service = ReviewService(config, resolver="reviewer", coordinator_api=fake)
    app.include_router(create_router(service), prefix="/api/ingestion")

    try:
        with TestClient(app) as client:
            client.post("/api/ingestion/run/start")
            wait_until_idle(client)
            response = client.get("/api/ingestion/evidence/run-1/concept-1")
    finally:
        service.close()

    assert response.status_code == 200
    assert response.content == b"page-nine-bytes"


def test_evidence_endpoint_404s_for_a_proposal_with_no_photo(
    tmp_path: Path,
) -> None:
    """A typed vault-note highlight (no `photo_page_id`) has nothing to
    serve -- this is the ordinary case, not a broken one, so it must fail
    cleanly rather than serving whatever the last image-review item was."""
    fake = FakeCoordinator(knowledge_proposal_run_view(photo_page_id=None))
    app, service = mounted_service(tmp_path, fake)

    try:
        with TestClient(app) as client:
            client.post("/api/ingestion/run/start")
            wait_until_idle(client)
            response = client.get("/api/ingestion/evidence/run-1/concept-1")
    finally:
        service.close()

    assert response.status_code == 404


def test_report_is_available_from_the_mounted_router(tmp_path: Path) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"photo")
    fake = FakeCoordinator(run_view(photo))
    app, service = mounted_service(tmp_path, fake)

    try:
        with TestClient(app) as client:
            report = client.get("/api/ingestion/run/run-1/report")
    finally:
        service.close()

    body = report.json()
    assert body["terminal_result"] == "complete"
    assert body["run_id"] == "run-1"
    # The server-side report file location is not a fact about the run.
    assert "path" not in body
    # Absent groups are described as empty rather than omitted, so the
    # diagnostics surface can state "none" instead of inferring it.
    assert body["discrepancies"] == []
    assert body["progress"] == {
        "intake_total": 0,
        "intake_resolved": 0,
        "envelopes_flagged": 0,
        "envelopes_resolved": 0,
    }


def test_a_failed_operation_is_named_so_the_failure_is_attributable(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"photo")
    fake = FakeCoordinator(run_view(photo))
    fake.fail_with = "the coordinator could not reach Neo4j"
    app, service = mounted_service(tmp_path, fake)

    try:
        with TestClient(app) as client:
            client.post("/api/ingestion/run/start")
            settled = wait_until_idle(client)
    finally:
        service.close()

    operation = settled["operation"]
    assert operation["state"] == "failed"
    assert operation["name"] == "start"
    assert operation["error"] == "the coordinator could not reach Neo4j"
    # A failure must not leave the revision advanced; nothing durable happened.
    assert operation["revision"] == 0


def test_a_named_failure_is_cleared_when_the_next_operation_starts(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"photo")
    fake = FakeCoordinator(run_view(photo))
    fake.fail_with = "transient stage failure"
    app, service = mounted_service(tmp_path, fake)

    try:
        with TestClient(app) as client:
            client.post("/api/ingestion/run/start")
            assert wait_until_idle(client)["operation"]["name"] == "start"

            fake.fail_with = None
            client.post("/api/ingestion/run/retry")
            recovered = wait_until_idle(client)
    finally:
        service.close()

    assert recovered["operation"]["state"] == "idle"
    assert recovered["operation"]["name"] is None
    assert recovered["operation"]["error"] is None
    assert recovered["operation"]["revision"] == 1


def test_optional_resolver_and_note_are_forwarded_for_t19(tmp_path: Path) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"photo")
    fake = FakeCoordinator(run_view(photo))
    app, service = mounted_service(tmp_path, fake)
    body = decision_body()
    body.update({"resolver": "aryaman", "note": "Evidence supports this."})

    try:
        with TestClient(app) as client:
            client.post("/api/ingestion/run/start")
            wait_until_idle(client)
            assert (
                client.post("/api/ingestion/run/decision", json=body).status_code
                == 202
            )
            wait_until_idle(client)
    finally:
        service.close()

    assert fake.decisions[0].resolver == "aryaman"
    assert fake.decisions[0].note == "Evidence supports this."


def test_run_level_phase_handoff_accepts_the_coordinator_empty_item_id(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"photo")
    fake = FakeCoordinator(run_view(photo))
    app, service = mounted_service(tmp_path, fake)
    body = decision_body()
    body.update({"item_id": "", "gate": "phase_handoff", "action": "continue", "payload": {}})

    try:
        with TestClient(app) as client:
            client.post("/api/ingestion/run/start")
            wait_until_idle(client)
            assert (
                client.post("/api/ingestion/run/decision", json=body).status_code
                == 202
            )
            wait_until_idle(client)
    finally:
        service.close()

    assert fake.decisions[0].item_id == ""
    assert fake.decisions[0].action == "continue"
