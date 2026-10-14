"""FastAPI router boundary for the synchronous repository coordinator.

The coordinator remains the only state machine. This module serializes its
mutating calls onto one worker and exposes only the latest immutable RunView.

It deliberately owns neither a FastAPI application nor a frontend or port.
The AI OS gateway mounts :func:`create_router` under ``/api/ingestion``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from enum import Enum
import os
from pathlib import Path
from threading import RLock
from typing import Annotated, Any, Literal, Protocol, TypeAlias, cast

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ingestion import coordinator
from ingestion.config import (
    IngestionConfig,
    IntakeConfig,
    central_database_root,
    load_root_env,
)
from ingestion.coordinator.report import RunReportView
from ingestion.coordinator.state import DecisionRequest, RunView
from ingestion.sources.page_scanner import store as page_scanner_store
from ingestion.text_cleanup.store import (
    DuplicateMappingError,
    MappingNotFoundError,
    MappingRecord,
    MappingRepository,
)


FRONTEND_CONTRACT_VERSION = "component6.v1"


class CoordinatorAPI(Protocol):
    def start_run(self, config: IngestionConfig, *, resolver: str) -> RunView: ...

    def submit_decision(
        self, config: IngestionConfig, decision: DecisionRequest
    ) -> RunView: ...

    def retry(self, config: IngestionConfig) -> RunView: ...

    def run_report(
        self, config: IngestionConfig, run_id: str | None = None
    ) -> RunReportView: ...


class ServiceBusyError(RuntimeError):
    pass


class ServiceStaleError(RuntimeError):
    pass


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(cast(Any, value)))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    return value


class ReviewService:
    """Serialize coordinator mutations and retain only its latest view."""

    def __init__(
        self,
        config: IngestionConfig,
        *,
        resolver: str,
        coordinator_api: CoordinatorAPI = coordinator,
    ) -> None:
        self.config = config
        self.resolver = resolver
        self.api = coordinator_api
        # Independent of any particular run's CleanupGate (which is
        # per-RunCoordinator and only exists while a run is active) --
        # mappings must be manageable regardless of run state.
        self.mappings = MappingRepository(config.text_cleanup_db_path)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cockpit")
        self._lock = RLock()
        self._future: Future[RunView] | None = None
        self._operation: str | None = None
        # The name of the operation that raised. Kept separately from
        # ``_operation`` because that field also means "in flight" -- retaining
        # it there would report a failed operation as permanently submitting.
        self._failed_operation: str | None = None
        self._latest: RunView | None = None
        self._error: str | None = None
        self._revision = 0

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _complete(self, future: Future[RunView]) -> None:
        with self._lock:
            try:
                self._latest = future.result()
                self._error = None
                self._revision += 1
            except Exception as error:  # The HTTP poll surface owns presentation.
                self._error = str(error)
                # A failure is only attributable if the poller can still name
                # the operation that produced it. An operation can start and
                # fail between two polls, so the name cannot be recovered
                # client-side.
                self._failed_operation = self._operation
            finally:
                self._operation = None

    def _submit(self, operation: str, call: Callable[[], RunView]) -> dict[str, Any]:
        with self._lock:
            if self._operation is not None:
                raise ServiceBusyError("another coordinator operation is in flight")
            self._operation = operation
            self._error = None
            self._failed_operation = None
            self._future = self._executor.submit(call)
            self._future.add_done_callback(self._complete)
            return self.snapshot()

    def start(self) -> dict[str, Any]:
        return self._submit(
            "start",
            lambda: self.api.start_run(self.config, resolver=self.resolver),
        )

    def decide(self, request: "DecisionBody") -> dict[str, Any]:
        with self._lock:
            if (
                request.expected_revision is not None
                and request.expected_revision != self._revision
            ):
                raise ServiceStaleError(
                    f"stale decision revision {request.expected_revision}; "
                    f"current revision is {self._revision}"
                )
        decision = DecisionRequest(
            run_id=request.run_id,
            item_id=request.item_id,
            gate=request.gate,
            action=request.action,
            payload=request.payload,
            resolver=request.resolver.strip() or self.resolver,
            note=request.note,
        )
        return self._submit(
            "decision", lambda: self.api.submit_decision(self.config, decision)
        )

    def retry(self) -> dict[str, Any]:
        return self._submit("retry", lambda: self.api.retry(self.config))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            busy = self._operation is not None
            return {
                "contract_version": FRONTEND_CONTRACT_VERSION,
                "view": _jsonable(self._latest),
                "reviewer": self.resolver,
                "operation": {
                    "state": "submitting" if busy else ("failed" if self._error else "idle"),
                    # While in flight this names the running operation; after a
                    # failure it names the operation that failed, so the error
                    # surface can attribute it. Idle-and-clean reports no name.
                    "name": self._operation
                    or (self._failed_operation if self._error else None),
                    "error": self._error,
                    "revision": self._revision,
                },
            }

    def evidence_path(self, run_id: str, item_id: str) -> Path:
        with self._lock:
            view = self._latest
            pending = view.pending if view is not None else None
            if (
                view is None
                or view.run_id != run_id
                or pending is None
                or pending.item_id != item_id
            ):
                raise FileNotFoundError("image evidence is not current")
            if pending.adapter == "image_ocr":
                path = Path(str(pending.payload.get("photo_path") or ""))
            elif pending.adapter == "knowledge_proposal":
                # A knowledge proposal's highlight may come from a
                # photographed page (`photo_page_id` set by
                # `_proposal_photo_evidence` in coordinator.py) or from a
                # typed vault note (no photo at all) -- the second case is
                # not an error, just nothing to serve.
                page_id = pending.payload.get("photo_page_id")
                if page_id is None:
                    raise FileNotFoundError("this proposal has no photographed source page")
                page = page_scanner_store.get_page(
                    self.config.page_scanner_db_path, int(cast(int, page_id))
                )
                path = Path(str((page or {}).get("image_path") or ""))
            else:
                raise FileNotFoundError("image evidence is not current")
        if not path.is_file():
            raise FileNotFoundError("current image evidence is unavailable")
        return path


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    # The deliberate intake-to-knowledge handoff is a run-level decision and
    # therefore uses the coordinator's canonical empty item id.
    item_id: str
    gate: str = Field(min_length=1)
    action: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    resolver: str = ""
    note: str = ""
    expected_revision: int | None = Field(default=None, ge=0)


class OperationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    name: str | None
    error: str | None
    revision: int = Field(ge=0)


class StageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    status: str
    detail: dict[str, Any]


class PayloadBody(BaseModel):
    """Forward-compatible base for coordinator-owned outbound payloads."""

    model_config = ConfigDict(extra="allow")


class BookIdentityPayload(PayloadBody):
    proposed_title: str | None = None
    proposed_author: str | None = None
    proposed_year: int | str | None = None
    confidence: str | float | None = None
    meta_source: str | None = None
    photo_count: int = Field(ge=0)
    resolved_slug: str | None = None


class ImagePassageBody(PayloadBody):
    index: int = Field(ge=0)
    ocr_text: str
    edited_text: str
    bbox: list[float] | None = None
    min_conf: float | None = None


class ImageOcrPayload(PayloadBody):
    photo_path: str
    page_number: int | None = None
    passages: list[ImagePassageBody]
    conf_ratio: float | None = None
    blur_score: float | None = None
    glare_score: float | None = None


class TextFilePayload(PayloadBody):
    source_path: str
    title: str | None = None
    extraction_method: str | None = None
    approval_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    markdown_text: str


class PhaseHandoffPayload(PayloadBody):
    discovered: int
    published: int
    discarded: int
    retake: int
    duplicate: int
    failed: int
    note_paths: list[str]


class ReviewSignalBody(PayloadBody):
    code: str
    scope: str
    detail: Any = None
    proposal_id: str | None = None


class KnowledgeEnvelopePayload(PayloadBody):
    envelope_level: Literal[True]
    review_signals: list[ReviewSignalBody]
    source_record_id: str
    highlight_index: int | None = None
    highlight_text: str | None = None
    model_confidence: float | str | None = None


class SiblingProposalBody(PayloadBody):
    """A read-only preview of another proposal from the same envelope.

    Lets the shell show every proposal derived from one highlight on a single
    screen without re-fetching or re-rendering the shared highlight/evidence
    context per proposal. Each sibling is still decided through its own
    `/run/decision` call once it becomes the active `proposal_id` -- this is
    a display aid, not a bulk-decision channel.
    """

    proposal_id: str
    proposal_type: str
    status: str
    summary: str


class PhotoPassageBody(PayloadBody):
    """One OCR'd passage box on the source page, for the read-only overlay
    shown alongside a proposal review. The pipeline does not track which
    specific passage backs a given proposal's evidence quote, so every
    passage on the page is offered -- a reviewer locates their highlight
    among them visually, the same way ImageReview.tsx already does."""

    bbox: list[float] | None = None
    ocr_text: str = ""


class KnowledgeProposalPayload(PayloadBody):
    envelope_id: str
    proposal_id: str
    proposal_type: str
    proposal: dict[str, Any]
    source_note_path: str | None = None
    origin_kind: str | None = None
    highlight_index: int | None = None
    highlight_text: str | None = None
    evidence_quote: str | None = None
    evidence_start_char: int | None = None
    evidence_end_char: int | None = None
    proposal_confidence: float | str | None = None
    envelope_confidence: float | str | None = None
    signals: list[ReviewSignalBody]
    sibling_proposals: list[SiblingProposalBody]
    # Set only when `origin_kind == "page_scanner"` and the source page is
    # still resolvable -- absent for the common case (a typed vault note),
    # which has no photo and is not an error.
    photo_page_id: int | None = None
    photo_page_number: int | None = None
    photo_passages: list[PhotoPassageBody] = Field(default_factory=list)


class CleanupOccurrenceBody(PayloadBody):
    occurrence_id: str
    ordinal: int = Field(ge=1)
    total: int = Field(ge=1)
    passage_index: int | None = None
    base_start: int = Field(ge=0)
    base_end: int
    current_start: int = Field(ge=0)
    current_end: int
    original_text: str
    proposed_text: str
    context_before: str
    context_after: str
    before_sentence: str
    after_sentence: str
    current_decision: str | None = None
    mapping_id: str | None = None
    proposal_source: str

    @model_validator(mode="after")
    def _ordered_offsets(self) -> "CleanupOccurrenceBody":
        if self.base_end < self.base_start:
            raise ValueError("base_end must be >= base_start")
        if self.current_end < self.current_start:
            raise ValueError("current_end must be >= current_start")
        return self


class CleanupReviewPayload(PayloadBody):
    state: Literal["review"]
    source_kind: Literal["image", "text_file", "typed_highlight"]
    phase: Literal["abbreviation", "spelling"]
    interaction_revision: int = Field(ge=0)
    working_draft_revision: int = Field(ge=0)
    occurrence: CleanupOccurrenceBody
    authoritative_sentence: str
    authoritative_working_text: str
    can_continue: bool


class CleanupUnavailablePayload(PayloadBody):
    state: Literal["unavailable"]
    source_kind: Literal["image", "text_file", "typed_highlight"]
    phase: Literal["spelling"]
    interaction_revision: int = Field(ge=0)
    working_draft_revision: int = Field(ge=0)
    error: str


class PendingBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    item_type: str
    gate: str
    allowed_actions: list[str]
    blocking_reason: str


class BookIdentityPending(PendingBase):
    adapter: Literal["book_identity"]
    payload: BookIdentityPayload


class ImageOcrPending(PendingBase):
    adapter: Literal["image_ocr"]
    payload: ImageOcrPayload


class TextFilePending(PendingBase):
    adapter: Literal["text_file"]
    payload: TextFilePayload


class PhaseHandoffPending(PendingBase):
    adapter: Literal["phase_handoff"]
    payload: PhaseHandoffPayload


class KnowledgeProposalPending(PendingBase):
    adapter: Literal["knowledge_proposal"]
    payload: KnowledgeEnvelopePayload | KnowledgeProposalPayload


class CleanupPending(PendingBase):
    adapter: Literal["cleanup"]
    payload: Annotated[
        CleanupReviewPayload | CleanupUnavailablePayload,
        Field(discriminator="state"),
    ]


PendingBody: TypeAlias = Annotated[
    BookIdentityPending
    | ImageOcrPending
    | TextFilePending
    | PhaseHandoffPending
    | KnowledgeProposalPending
    | CleanupPending,
    Field(discriminator="adapter"),
]


class ProgressBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intake_total: int = Field(ge=0)
    intake_resolved: int = Field(ge=0)
    envelopes_flagged: int = Field(ge=0)
    envelopes_resolved: int = Field(ge=0)


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    message: str
    retryable: bool


class ViewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    stage: str
    stage_status: str
    stages: list[StageBody]
    pending: PendingBody | None
    progress: ProgressBody
    last_error: ErrorBody | None
    terminal_result: str | None


class RunSnapshotBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    view: ViewBody | None
    reviewer: str
    operation: OperationBody


# The durable run report is JSON read back off disk, possibly written by an
# earlier version of the coordinator. Its models therefore extend PayloadBody
# and tolerate extra keys: refusing to describe a finished run because it
# carries one unrecognized field would break the surface whose entire job is
# explaining what happened. The live-view models above stay strict because they
# are built in-process by this same module.
class ReportErrorBody(PayloadBody):
    stage: str
    message: str
    retryable: bool = True


class ReportStageBody(PayloadBody):
    stage: str
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ReportProgressBody(PayloadBody):
    intake_total: int = 0
    intake_resolved: int = 0
    envelopes_flagged: int = 0
    envelopes_resolved: int = 0


class ReportIntakeBody(PayloadBody):
    discovered: int = 0
    published: int = 0
    discarded: int = 0
    retake: int = 0
    duplicate: int = 0
    failed: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)
    gates: list[dict[str, Any]] = Field(default_factory=list)


class ReportCaptureCountsBody(PayloadBody):
    total: int = 0
    new: int = 0
    duplicate: int = 0


class ReportReviewCountsBody(PayloadBody):
    approve: int = 0
    edit: int = 0
    reject: int = 0
    still_blocked: int = 0


class RunReportBody(PayloadBody):
    """The durable record a finished run leaves behind.

    This is the report's own ``data`` mapping. The on-disk path is deliberately
    not exposed: it is a server filesystem detail, not a fact about the run.
    """

    run_id: str
    terminal_result: str | None = None
    failed_from: str | None = None
    last_error: ReportErrorBody | None = None
    stages: list[ReportStageBody] = Field(default_factory=list)
    intake: ReportIntakeBody = Field(default_factory=ReportIntakeBody)
    vault_notes_written: list[str] = Field(default_factory=list)
    capture: list[dict[str, Any]] = Field(default_factory=list)
    capture_counts: ReportCaptureCountsBody = Field(
        default_factory=ReportCaptureCountsBody
    )
    processing: list[dict[str, Any]] = Field(default_factory=list)
    processing_counts: dict[str, int] = Field(default_factory=dict)
    review: ReportReviewCountsBody = Field(default_factory=ReportReviewCountsBody)
    dispatch_counts: dict[str, int] = Field(default_factory=dict)
    retryable_failures: list[dict[str, Any]] = Field(default_factory=list)
    discrepancies: list[str] = Field(default_factory=list)
    progress: ReportProgressBody = Field(default_factory=ReportProgressBody)


class MappingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    shorthand: str
    expansion: str
    case_sensitive: bool
    created_at: str
    updated_at: str


class MappingListBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[MappingBody]


class MappingCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shorthand: str = Field(min_length=1)
    expansion: str = Field(min_length=1)
    case_sensitive: bool = True


class MappingUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expansion: str = Field(min_length=1)


def _mapping_body(record: MappingRecord) -> MappingBody:
    return MappingBody(
        id=record.id,
        shorthand=record.shorthand,
        expansion=record.expansion,
        case_sensitive=record.case_sensitive,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def config_from_environment() -> IngestionConfig:
    load_root_env()
    database = Path(
        os.environ.get("INGESTION_DATABASE_ROOT", "") or central_database_root()
    ).expanduser().resolve()
    drop = Path(
        os.environ.get("INGESTION_DROP_FOLDER", "")
        or IntakeConfig().drop_folder
    ).expanduser().resolve()
    vault_value = os.environ.get("INGESTION_VAULT_PATH", "").strip()
    archive_value = os.environ.get("INGESTION_POST_PUBLISH_ROOT", "").strip()
    return IngestionConfig(
        database_root=database,
        intake=IntakeConfig(
            drop_folder=drop,
            vault_path=Path(vault_value).expanduser().resolve() if vault_value else None,
            post_publish_root=(
                Path(archive_value).expanduser().resolve() if archive_value else None
            ),
            cleanup_provider=os.environ.get("INGESTION_CLEANUP_PROVIDER", "gemma"),
        ),
    )


def create_router(service: ReviewService) -> APIRouter:
    """Expose ingestion HTTP operations without owning a FastAPI process."""

    router = APIRouter()

    @router.get("/run", response_model=RunSnapshotBody)
    def get_run() -> dict[str, Any]:
        return service.snapshot()

    @router.post(
        "/run/start",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=RunSnapshotBody,
    )
    def start_run() -> dict[str, Any]:
        try:
            return service.start()
        except ServiceBusyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post(
        "/run/decision",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=RunSnapshotBody,
    )
    def submit_decision(body: DecisionBody) -> dict[str, Any]:
        try:
            return service.decide(body)
        except ServiceBusyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ServiceStaleError as error:
            raise HTTPException(status_code=412, detail=str(error)) from error

    @router.post(
        "/run/retry",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=RunSnapshotBody,
    )
    def retry_run() -> dict[str, Any]:
        try:
            return service.retry()
        except ServiceBusyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/run/{run_id}/report", response_model=RunReportBody)
    def report(run_id: str) -> dict[str, Any]:
        try:
            view = service.api.run_report(service.config, run_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return cast(dict[str, Any], _jsonable(view.data))

    @router.get("/evidence/{run_id}/{item_id}")
    def evidence(run_id: str, item_id: str) -> Response:
        try:
            path = service.evidence_path(run_id, item_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    # Component 8 (C8-C5): manual shorthand+expansion mapping management,
    # independent of any live run -- reviewers can create/edit/delete
    # mappings whether or not a coordinator run is currently active.
    @router.get("/cleanup/mappings", response_model=MappingListBody)
    def list_mappings(query: str = "") -> MappingListBody:
        return MappingListBody(
            mappings=[_mapping_body(record) for record in service.mappings.search(query)]
        )

    @router.post(
        "/cleanup/mappings",
        status_code=status.HTTP_201_CREATED,
        response_model=MappingBody,
    )
    def create_mapping(body: MappingCreateBody) -> MappingBody:
        try:
            record = service.mappings.create(
                body.shorthand, body.expansion, case_sensitive=body.case_sensitive
            )
        except DuplicateMappingError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _mapping_body(record)

    @router.patch("/cleanup/mappings/{mapping_id}", response_model=MappingBody)
    def update_mapping(mapping_id: str, body: MappingUpdateBody) -> MappingBody:
        try:
            record = service.mappings.edit(mapping_id, expansion=body.expansion)
        except MappingNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _mapping_body(record)

    @router.delete(
        "/cleanup/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    def delete_mapping(mapping_id: str) -> Response:
        try:
            service.mappings.delete(mapping_id)
        except MappingNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
