from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, cast
import uuid

from gateway.ingestion.config import IngestionConfig
from gateway.ingestion.coordinator.errors import (
    GateUnavailable,
    IllegalDecisionError,
    IllegalStageTransition,
    PreflightFailed,
)
from gateway.ingestion.coordinator.gates import (
    BookMetadataGate,
    CleanupGate,
    ContentApprovalGate,
    PhaseHandoffGate,
    ReviewGate,
)
from gateway.ingestion.coordinator.preflight import CheckResult, run_preflight
from gateway.ingestion.coordinator.report import write_report
from gateway.ingestion.coordinator.stages import RunStage, StageStatus, assert_transition
from gateway.ingestion.coordinator.state import (
    DecisionRequest,
    ErrorView,
    PendingDecision,
    ProgressView,
    RunStateStore,
    RunView,
    StageView,
)
from gateway.ingestion.intake.base import Extractor, IntakeResult
from gateway.ingestion.intake.extractors import ImageExtractor
from gateway.ingestion.intake.extractors.image import IMAGE_EXTENSIONS
from gateway.ingestion.intake.funnel import (
    PreparedFile,
    PostPublishMover,
    VaultWriter,
    default_extractors,
    move_published_source,
    prepare_file,
    publish_prepared,
    route_file,
    scan_drop_folder,
)
from gateway.ingestion.models import ProposalReviewDecision
from gateway.ingestion.publish.vault_writer import (
    approved_intake_result,
    append_book_highlight_passages,
    finalize_published_page,
    page_scanner_photo_destination,
    write_note_to_vault,
)
from gateway.ingestion.runner import IngestionSession, ingestion_session
from gateway.ingestion.sources import book_metadata, obsidian
from gateway.ingestion.sources.obsidian import capture_book_highlights, capture_obsidian_vault
from gateway.ingestion.sources.page_scanner import store as page_store
from gateway.ingestion.text_cleanup.store import MappingRepository


SessionFactory = Callable[[IngestionConfig], AbstractContextManager[IngestionSession]]
PreflightRunner = Callable[[IngestionConfig], tuple[CheckResult, ...]]
CaptureFunction = Callable[..., list[Any]]


def _sort_key(path: Path) -> tuple[str, str]:
    return path.name.casefold(), path.name


def _proposal_summary(proposal_type: str, proposal: Mapping[str, Any]) -> str:
    """One-line display text for a proposal, keyed by its own type's fields
    (models.py:121-190) -- used only for the sibling-proposal preview list, so
    a reviewer can see what else came from this highlight without switching
    screens. Never used to decide anything; the full `proposal` dict still
    backs the actual review payload for whichever proposal is active."""
    if proposal_type == "concept":
        return str(proposal.get("label") or "")
    if proposal_type == "claim":
        return str(proposal.get("text") or "")
    if proposal_type == "relation":
        subject = proposal.get("subject") or ""
        predicate = proposal.get("predicate") or ""
        object_ = proposal.get("object") or ""
        return f"{subject} {predicate} {object_}".strip()
    return ""


def _available(destination: Path) -> Path:
    if not destination.exists():
        return destination
    counter = 2
    while True:
        candidate = destination.with_name(
            f"{destination.stem}-{counter}{destination.suffix}"
        )
        if not candidate.exists():
            return candidate
        counter += 1


class RunCoordinator:
    """Strictly sequential owner of one repository ingestion invocation."""

    def __init__(
        self,
        config: IngestionConfig,
        *,
        resolver: str,
        preflight_runner: PreflightRunner = run_preflight,
        extractors: Sequence[Extractor] | None = None,
        session_factory: SessionFactory = ingestion_session,
        capture_function: CaptureFunction = capture_obsidian_vault,
        vault_writer: VaultWriter = write_note_to_vault,
        gates: Sequence[ReviewGate] | None = None,
    ) -> None:
        if not resolver.strip():
            raise ValueError("resolver cannot be blank")
        if config.intake is None:
            raise ValueError("IngestionConfig.intake is required for repository runs")
        self.config = config
        self.resolver = resolver
        self.run_id = str(uuid.uuid4())
        self.state_store = RunStateStore(config.coordinator_db_path, self.run_id)
        self._preflight_runner = preflight_runner
        self._session_factory = session_factory
        self._capture = capture_function
        self._vault_writer = vault_writer
        gateway = self._shared_gateway() if extractors is None or gates is None else None
        self._extractors = (
            tuple(extractors) if extractors is not None else self._production_extractors(gateway)
        )
        self._gates = tuple(gates) if gates is not None else (
            BookMetadataGate(config.page_scanner_db_path),
            CleanupGate(
                mapping_repository=MappingRepository(config.text_cleanup_db_path),
                chat_client=gateway,
                spelling_profile=config.intake.spelling_review_profile,
            ),
            ContentApprovalGate(config.page_scanner_db_path),
        )
        self.stage = RunStage.CREATED
        self.stage_status = StageStatus.RUNNING
        self.pending: PendingDecision | None = None
        self.last_error: ErrorView | None = None
        self.terminal_result: str | None = None
        self._stage_views: dict[RunStage, StageView] = {
            RunStage.CREATED: StageView(RunStage.CREATED, StageStatus.DONE, {})
        }
        self._failed_from: RunStage | None = None
        self._items: list[Path] = []
        self._item_index = 0
        self._prepared: PreparedFile | None = None
        self._seen_hashes: set[str] = set()
        self._intake_did_work = False
        self._intake_counts: dict[str, int] = {
            key: 0
            for key in ("discovered", "published", "discarded", "retake", "duplicate", "failed")
        }
        self._item_results: list[dict[str, Any]] = []
        self._gate_events: list[dict[str, Any]] = []
        self._captured: list[Any] = []
        self._captured_passages: list[Any] = []
        self._processed: list[Any] = []
        self._dispatch_outcomes: list[Any] = []
        self._stale_dispatch_failures: list[dict[str, Any]] = []
        self._envelopes_flagged = 0
        self._envelopes_resolved = 0
        self._review_counts = {"approve": 0, "edit": 0, "reject": 0}
        self._resolved_vault: Path | None = None

    @staticmethod
    def _shared_gateway() -> Any:
        try:
            from gateway.ingestion.runner import _shared_gateway_client

            return _shared_gateway_client()
        except Exception:
            # Preflight reports the real dependency failure before extraction
            # or cleanup ever runs; a missing gateway here becomes an
            # explicit unavailable cleanup state rather than a crash.
            return None

    def _production_extractors(self, gateway: Any) -> tuple[Extractor, ...]:
        intake = self.config.intake
        assert intake is not None
        defaults = default_extractors()
        return (
            ImageExtractor(
                clean=True,
                cleanup_client=gateway,
                cleanup_profile=intake.cleanup_profile,
                metadata_client=None,
            ),
            *defaults[1:],
        )

    def close(self) -> None:
        """Release only the process lock; durable work remains in its owner store."""

        self.state_store.release_lock()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def view(self) -> RunView:
        return RunView(
            run_id=self.run_id,
            stage=self.stage,
            stage_status=self.stage_status,
            stages=tuple(self._stage_views.values()),
            pending=self.pending,
            progress=ProgressView(
                intake_total=self._intake_counts["discovered"],
                intake_resolved=sum(
                    self._intake_counts[key]
                    for key in ("published", "discarded", "retake", "duplicate")
                ),
                envelopes_flagged=self._envelopes_flagged,
                envelopes_resolved=self._envelopes_resolved,
            ),
            last_error=self.last_error,
            terminal_result=self.terminal_result,
        )

    def _set_status(
        self, status: StageStatus, detail: Mapping[str, Any] | None = None
    ) -> None:
        self.stage_status = status
        self._stage_views[self.stage] = StageView(self.stage, status, detail or {})

    def _transition(self, target: RunStage) -> None:
        assert_transition(self.stage, target)
        if self.stage_status == StageStatus.RUNNING:
            self._set_status(StageStatus.DONE)
        self.stage = target
        self.stage_status = StageStatus.RUNNING
        self.pending = None
        self._stage_views[target] = StageView(target, StageStatus.RUNNING, {})

    def _fail(
        self,
        error: Exception,
        *,
        failed_from: RunStage | None = None,
    ) -> RunView:
        actual_stage = self.stage
        retry_stage = failed_from or actual_stage
        if self.stage != RunStage.FAILED:
            if retry_stage == actual_stage:
                self._set_status(StageStatus.FAILED, {"error": str(error)})
            else:
                # A deferred integrity check can discover at the final stage
                # that earlier processing work is still unresolved.  Dispatch
                # itself succeeded, so keep that stage truthful and attribute
                # the retry to the stage that can actually recover the work.
                if self.stage_status == StageStatus.RUNNING:
                    self._set_status(StageStatus.DONE)
                prior = self._stage_views.get(retry_stage)
                detail = dict(prior.detail) if prior is not None else {}
                detail["error"] = str(error)
                self._stage_views[retry_stage] = StageView(
                    retry_stage, StageStatus.FAILED, detail
                )
            self._transition(RunStage.FAILED)
        self._failed_from = retry_stage
        self.last_error = ErrorView(retry_stage, str(error), True)
        self._set_status(
            StageStatus.FAILED,
            {"failed_from": retry_stage.value, "error": str(error)},
        )
        if retry_stage == RunStage.INTAKE_ITEM:
            self._intake_counts["failed"] += 1
        # A failed run is a finished run: it writes the report you most want to
        # read and gives up the lock, so a fix made outside the app can be
        # followed by a clean `start_run()` without restarting Python. A report
        # that cannot be written must not replace the failure it was recording
        # — the lock is released either way, and the original error is what the
        # caller gets back.
        try:
            self._finish("failed")
        except Exception as report_error:
            self.terminal_result = "failed"
            self._set_status(
                StageStatus.FAILED,
                {
                    "failed_from": retry_stage.value,
                    "error": str(error),
                    "report_error": str(report_error),
                },
            )
        return self.view()

    def _resolve_vault(self) -> Path:
        if self._resolved_vault is None:
            intake = self.config.intake
            assert intake is not None
            self._resolved_vault = (
                intake.vault_path or obsidian.discover_vault_path()
            ).expanduser().resolve()
        return self._resolved_vault

    def _archive_destination(
        self, source: Path, page: Mapping[str, Any] | None
    ) -> Path:
        """Resolve where one published source file lands, for both callers.

        `_publish_item()` and the next start's recovery of a row with no
        `moved_at` both come through here, so the live path and the recovery
        path cannot drift into archiving the same photo to two places.
        """

        intake = self.config.intake
        assert intake is not None
        if page is not None and source.suffix.lower() in IMAGE_EXTENSIONS:
            metadata: dict[str, Any] = json.loads(str(page.get("book_meta") or "{}"))
            destination: Path = page_scanner_photo_destination(
                source,
                IntakeResult(
                    markdown_text="",
                    title=source.stem or "page",
                    needs_approval=False,
                    frontmatter={"book_meta": metadata},
                ),
                database_root=self.config.database_root,
            )
            return destination
        root = intake.post_publish_root or self.config.database_root / "intake_processed"
        return _available(root / source.name)

    def _settle_unfinished_publication(self) -> None:
        publication = self.state_store.unfinished_publication()
        if publication is None:
            return
        source, note = publication.source_path, publication.note_path
        if not note.exists():
            self.state_store.finish_publication(
                publication.id, None, outcome="abandoned"
            )
            return
        if not source.exists():
            self.state_store.finish_publication(publication.id, None)
            return
        page = page_store.get_page_by_file_hash(
            self.config.page_scanner_db_path, publication.content_hash
        )
        destination = self._archive_destination(source, page)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), destination)
        if page is not None and page.get("status") == "reviewed":
            finalize_published_page(
                self.config.page_scanner_db_path,
                int(page["id"]),
                moved_to=destination,
            )
        self.state_store.finish_publication(publication.id, destination)

    def _discover(self) -> None:
        intake = self.config.intake
        assert intake is not None
        page_store.init_db(self.config.page_scanner_db_path)
        self._settle_unfinished_publication()
        candidates: list[Path] = []
        for path in scan_drop_folder(intake.drop_folder):
            # Dotfiles are never something you dropped in. `.DS_Store` at the
            # top level would otherwise be an unroutable file, which is a
            # mandatory failure — and macOS writes one into any folder you open.
            if path.name.startswith("."):
                continue
            if any(isinstance(extractor, ImageExtractor) and extractor.handles(path) for extractor in self._extractors):
                raise ValueError(
                    f"top-level image {path.name!r} must be placed in a folder for its book"
                )
            route_file(path, self._extractors)
            candidates.append(path)
        folders = sorted(
            (
                path
                for path in intake.drop_folder.iterdir()
                # Same rule one level up: `.Spotlight-V100` and a sync client's
                # cache directory are not book folders, and treating them as one
                # would fail every run on the files inside them.
                if path.is_dir() and not path.name.startswith(".")
            ),
            key=_sort_key,
        )
        for folder in folders:
            candidates.extend(self._book_folder_images(folder))

        self._items = []
        self._seen_hashes.clear()
        self._intake_counts["discovered"] = len(candidates)
        for path in candidates:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in self._seen_hashes:
                self._intake_counts["duplicate"] += 1
                self._item_results.append(
                    {"source_path": str(path), "content_hash": digest, "outcome": "duplicate"}
                )
                continue
            self._seen_hashes.add(digest)
            self._items.append(path)
        self._item_index = 0
        if not candidates:
            self._set_status(StageStatus.SKIPPED, {"discovered": 0})
        else:
            self._set_status(StageStatus.DONE, {"discovered": len(candidates)})

    def _book_folder_images(self, folder: Path) -> list[Path]:
        """List one book folder's photos, refusing anything that is not one.

        A PDF, a `.docx` or a nested folder sitting beside the photos is neither
        a page of this book nor something the run can quietly drop — this ticket
        exists to stop exactly that silent skip. Dotfiles are the one exception:
        macOS writes `.DS_Store` into any folder you open in Finder, and
        photographing a book means opening its folder.
        """

        images: list[Path] = []
        for path in sorted(folder.iterdir(), key=_sort_key):
            if path.name.startswith("."):
                continue
            if path.is_dir():
                if path.name == "_retake":
                    continue
                raise ValueError(
                    f"book folder {folder.name!r} contains a nested folder "
                    f"{path.name!r}; a book folder holds photos only"
                )
            if path.name == book_metadata.QUERY_FILE:
                continue
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                images.append(path)
                continue
            raise ValueError(
                f"book folder {folder.name!r} contains non-photo file "
                f"{path.name!r}; move it to the top level of the drop folder"
            )
        return images

    def _remap_book_folder(self, old_folder: Path, new_folder: Path) -> None:
        if old_folder == new_folder:
            return
        self._items = [
            new_folder / path.name if path.parent == old_folder else path
            for path in self._items
        ]

    def _page_for(self, prepared: PreparedFile) -> dict[str, Any] | None:
        return page_store.get_page_by_file_hash(
            self.config.page_scanner_db_path, prepared.content_hash
        )

    def _record_gate(
        self, prepared: PreparedFile, gate: str, status: str, **detail: Any
    ) -> None:
        self._gate_events.append(
            {
                "item_id": prepared.content_hash,
                "source_path": str(prepared.source_path),
                "gate": gate,
                "status": status,
                **detail,
            }
        )

    def _terminal_content_outcome(self, prepared: PreparedFile) -> str | None:
        if not prepared.result.needs_approval:
            return None
        page = self._page_for(prepared) if prepared.result.needs_approval else None
        if page is None:
            return None
        status = str(page.get("status") or "")
        return status if status in {"discarded", "retake", "published"} else None

    def _finish_item(
        self,
        prepared: PreparedFile,
        outcome: str,
        *,
        worked: bool = True,
        **detail: Any,
    ) -> None:
        # The one common completion point for every outcome (published,
        # discarded, retake) -- clearing here, not at the approve/discard/
        # retake decision itself, matters because the coordinator re-enters
        # _process_intake_item() at least once more after that decision
        # (status moves to "reviewed" before "published"), and an early
        # clear would make cleanup treat that re-entry as a brand new item.
        cleanup_gate = self._cleanup_gate()
        if cleanup_gate is not None:
            cleanup_gate.clear(prepared.content_hash)
        if outcome in self._intake_counts:
            self._intake_counts[outcome] += 1
        self._item_results.append(
            {
                "source_path": str(prepared.source_path),
                "content_hash": prepared.content_hash,
                "outcome": outcome,
                **detail,
            }
        )
        self._item_index += 1
        self._intake_did_work = self._intake_did_work or worked
        self._prepared = None
        self.pending = None

    def _publish_item(self, prepared: PreparedFile) -> None:
        intake = self.config.intake
        assert intake is not None
        page = self._page_for(prepared) if prepared.result.needs_approval else None
        active = prepared
        destination_map: dict[type[Extractor], PostPublishMover] = {}
        page_id: int | None = None
        if page is not None and page.get("status") == "reviewed":
            page_id = int(page["id"])
            photo_destination: Path | None = None
            if isinstance(prepared.extractor, ImageExtractor):
                photo_destination = self._archive_destination(
                    prepared.source_path, page
                )
            approved = approved_intake_result(
                self.config.page_scanner_db_path,
                page_id,
                prepared.result,
                photo_destination=photo_destination,
            )
            active = replace(prepared, result=approved)
            if photo_destination is not None:
                destination_map[type(prepared.extractor)] = (
                    cast(PostPublishMover, lambda _source, _result, destination=photo_destination: destination)
                )

        if type(active.extractor) not in destination_map:
            root = intake.post_publish_root or self.config.database_root / "intake_processed"
            destination_map[type(active.extractor)] = (
                cast(PostPublishMover, lambda source, _result, root=root: _available(root / source.name))
            )
        if page_id is not None and isinstance(prepared.extractor, ImageExtractor):
            # T63: a photo's marked passages accumulate into its book's
            # shared highlights document here, before the per-page note --
            # capture_book_highlights() turns them into highlights later, in
            # CAPTURE_OBSIDIAN. page_id alone is not specific to photos: a
            # generic text_file approval (e.g. a .fixture/PDF/DOCX result
            # needing approval) is parked in the same page-scanner store too,
            # and has no book to attach a highlights document to.
            #
            # This must precede the note write. T60's crash-safe publication
            # seam requires note write -> publication row to be consecutive;
            # putting this append between them reopened the exact duplicate-note
            # window the row closes. The append is page-marker idempotent, so a
            # crash here safely retries it while the source is still in place.
            append_book_highlight_passages(self._resolve_vault(), active.result)
        note_path = publish_prepared(
            self._resolve_vault(), active, write_note_to_vault=self._vault_writer
        )
        publication_id = self.state_store.add_publication(
            active.source_path, note_path, active.content_hash
        )
        moved_to = move_published_source(
            active,
            drop_folder=intake.drop_folder,
            post_publish_destination=destination_map,
        )
        if page_id is not None:
            finalize_published_page(
                self.config.page_scanner_db_path, page_id, moved_to=moved_to
            )
        self.state_store.finish_publication(publication_id, moved_to)
        self._finish_item(
            prepared,
            "published",
            note_path=str(note_path),
            moved_to=str(moved_to),
        )

    def _cleanup_gate(self) -> CleanupGate | None:
        return next(
            (gate for gate in self._gates if isinstance(gate, CleanupGate)), None
        )

    def _process_intake_item(self) -> bool:
        if self._item_index >= len(self._items):
            return True
        source = self._items[self._item_index]
        prepared = prepare_file(source, self._extractors)
        # A fresh prepare_file() re-extracts from the source file every time
        # this item is revisited (see submit_decision()'s return self.advance()
        # after a cleanup decision). Without this overlay, cleanup's in-memory
        # revised text would be silently replaced by the raw re-extraction on
        # every subsequent pass (component_8.md section 7.3).
        raw_result = prepared.result
        cleanup_gate = self._cleanup_gate()
        if cleanup_gate is not None:
            prepared = cleanup_gate.overlay(prepared)
        self._prepared = prepared

        if isinstance(prepared.extractor, ImageExtractor):
            book_gate = next(
                (gate for gate in self._gates if gate.name == "book_metadata"), None
            )
            if book_gate is not None:
                pending = book_gate.pending(prepared)
                if pending is not None:
                    self._record_gate(prepared, book_gate.name, "blocked")
                    self.pending = pending
                    self._set_status(
                        StageStatus.BLOCKED,
                        {"gate": pending.gate, "gates": tuple(self._gate_events)},
                    )
                    return False
                self._record_gate(prepared, book_gate.name, "skipped")
            old_folder = prepared.source_path.parent
            new_folder = book_metadata.finalize_resolved_folder(
                old_folder, db_path=self.config.page_scanner_db_path
            )
            self._remap_book_folder(old_folder, new_folder)
            if new_folder != old_folder:
                prepared = replace(prepared, source_path=new_folder / prepared.source_path.name)
                self._prepared = prepared

        terminal = self._terminal_content_outcome(prepared)
        if terminal in {"discarded", "retake"}:
            self._finish_item(prepared, terminal, worked=False)
            return True
        if terminal == "published":
            # A publication row never gates work, but the gate's own durable state
            # tells us this still-present discarded/manual copy is resolved.
            self._finish_item(prepared, "published", worked=False)
            return True

        for gate in self._gates:
            if gate.name == "book_metadata":
                continue
            try:
                pending = (
                    gate.pending(prepared, park_result=raw_result)
                    if isinstance(gate, ContentApprovalGate)
                    else gate.pending(prepared)
                )
            except GateUnavailable as error:
                # A gate reporting its own dependency unavailable is a run-level
                # failure, not a pending. This used to return a pending carrying
                # `{"error": ...}` under `adapter="cleanup"`, which no member of
                # the typed pending union can hold — `CleanupPending.payload` is
                # discriminated on `state`, so `GET /run` failed response-model
                # validation and the whole run became un-renderable. Component 8
                # called this out in advance: "Do not rely on the coordinator's
                # current generic `GateUnavailable` payload (`{"error": ...}`),
                # because that shape cannot satisfy the typed cleanup contract."
                # Failing loudly lands on the run's existing retryable-failure
                # surface, which is what T60 already describes for a mid-run
                # dependency outage: "You start Ollama, call `retry()`, and it
                # picks up the same photo."
                self._record_gate(prepared, gate.name, "failed", error=str(error))
                raise
            if pending is not None:
                self._record_gate(prepared, gate.name, "blocked")
                self.pending = pending
                self._set_status(
                    StageStatus.BLOCKED,
                    {"gate": pending.gate, "gates": tuple(self._gate_events)},
                )
                return False
            self._record_gate(prepared, gate.name, "skipped")
        self._publish_item(prepared)
        self._set_status(
            StageStatus.RUNNING,
            {"resolved": self._item_index, "total": len(self._items)},
        )
        return True

    def _proposal_photo_evidence(
        self, metadata: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Photo provenance for a proposal review, when the highlight came
        from a photographed page rather than a typed vault note.

        The pipeline does not track which specific passage on the page
        backs a given proposal's evidence quote (`capture_book_highlights`
        turns a whole page into one source with several highlights, and
        segmentation loses the passage boundary), so every passage on the
        page is offered rather than none: the reviewer locates their
        highlight among them visually, same as `ImageReview.tsx` already
        does for the earlier OCR-acceptance step. Absent entirely for the
        common case (a typed note has no photo); that is not an error.
        """
        empty: dict[str, Any] = {
            "photo_page_id": None,
            "photo_page_number": None,
            "photo_passages": [],
        }
        if metadata.get("origin_kind") != "page_scanner":
            return empty
        page_scanner_id = metadata.get("page_scanner_id")
        if page_scanner_id is None:
            return empty
        page = page_store.get_page(
            self.config.page_scanner_db_path, int(cast(int, page_scanner_id))
        )
        if page is None:
            return empty
        passages = page_store.get_passages(
            self.config.page_scanner_db_path, int(cast(int, page_scanner_id))
        )
        return {
            "photo_page_id": int(cast(int, page_scanner_id)),
            "photo_page_number": page.get("page_number"),
            "photo_passages": [
                {"bbox": passage.get("bbox"), "ocr_text": passage.get("ocr_text") or ""}
                for passage in passages
            ],
        }

    def _pending_proposal(self, session: IngestionSession) -> PendingDecision | None:
        reviews = session.pipeline.store.pending_reviews()
        if not reviews:
            return None
        review = reviews[0]
        pending_items = [item for item in review["items"] if item["status"] == "pending"]
        if not pending_items:
            envelope = review["envelope"]
            return PendingDecision(
                item_id=str(review["envelope_id"]),
                item_type="envelope",
                gate="proposal",
                adapter="knowledge_proposal",
                payload={
                    "envelope_level": True,
                    "review_signals": envelope.get("review_signals", []),
                    "source_record_id": review["source_record_id"],
                    "highlight_index": envelope.get("highlight_index"),
                    "highlight_text": envelope.get("highlight_text"),
                    "model_confidence": envelope.get("model_confidence"),
                },
                allowed_actions=("approve", "reject"),
                blocking_reason="semantic envelope requires review",
            )
        item = pending_items[0]
        envelope = review["envelope"]
        proposal = cast(dict[str, Any], item["original_proposal"])
        metadata = (
            dict(envelope["metadata"])
            if isinstance(envelope.get("metadata"), Mapping)
            else {}
        )
        evidence_values = proposal.get("evidence")
        evidence = (
            dict(evidence_values[0])
            if isinstance(evidence_values, list)
            and evidence_values
            and isinstance(evidence_values[0], Mapping)
            else {}
        )
        signal_values = envelope.get("review_signals")
        signals = [
            {
                "code": str(signal.get("code") or ""),
                "scope": str(signal.get("scope") or "envelope"),
                "detail": signal.get("detail"),
                **(
                    {"proposal_id": signal.get("proposal_id")}
                    if str(signal.get("scope") or "envelope") == "proposal"
                    else {}
                ),
            }
            for signal in signal_values
            if isinstance(signal, Mapping)
            and (
                str(signal.get("scope") or "envelope") != "proposal"
                or str(signal.get("proposal_id") or "")
                == str(item["proposal_id"])
            )
        ] if isinstance(signal_values, list) else []
        # Every other item in this same envelope, so the shell can render the
        # whole envelope's proposal list on one screen instead of forcing the
        # reviewer to re-read the shared highlight/evidence once per proposal.
        # Read-only: deciding a sibling still requires its own
        # `/run/decision` call once the coordinator surfaces it as `item`.
        siblings = [
            {
                "proposal_id": str(sibling["proposal_id"]),
                "proposal_type": str(sibling["proposal_type"]),
                "status": str(sibling["status"]),
                "summary": _proposal_summary(
                    str(sibling["proposal_type"]),
                    cast(dict[str, Any], sibling["original_proposal"]),
                ),
            }
            for sibling in review["items"]
            if str(sibling["proposal_id"]) != str(item["proposal_id"])
        ]
        photo_evidence = self._proposal_photo_evidence(metadata)
        return PendingDecision(
            item_id=str(item["proposal_id"]),
            item_type="proposal",
            gate="proposal",
            adapter="knowledge_proposal",
            payload={
                "envelope_id": str(review["envelope_id"]),
                "proposal_id": item["proposal_id"],
                "proposal_type": item["proposal_type"],
                "proposal": proposal,
                "source_note_path": metadata.get("vault_relative_path")
                or envelope.get("origin"),
                "origin_kind": metadata.get("origin_kind"),
                "highlight_index": envelope.get("highlight_index"),
                "highlight_text": envelope.get("highlight_text"),
                "evidence_quote": evidence.get("quote"),
                "evidence_start_char": evidence.get("normalized_char_start"),
                "evidence_end_char": evidence.get("normalized_char_end"),
                "proposal_confidence": proposal.get("model_confidence"),
                "envelope_confidence": envelope.get("model_confidence"),
                "signals": signals,
                "sibling_proposals": siblings,
                **photo_evidence,
            },
            allowed_actions=("approve", "edit", "reject"),
            blocking_reason="semantic proposal requires review",
        )

    def advance(self) -> RunView:
        if self.stage in {RunStage.COMPLETE, RunStage.FAILED}:
            return self.view()
        try:
            while True:
                if self.stage == RunStage.CREATED:
                    self._transition(RunStage.PREFLIGHT)
                elif self.stage == RunStage.PREFLIGHT:
                    checks = self._preflight_runner(self.config)
                    failed = [check for check in checks if not check.ok]
                    self._set_status(
                        StageStatus.FAILED if failed else StageStatus.DONE,
                        {"checks": [check.__dict__ for check in checks]},
                    )
                    if failed:
                        raise PreflightFailed(
                            "; ".join(f"{check.name}: {check.detail}" for check in failed)
                        )
                    self._transition(RunStage.DISCOVER_INTAKE)
                elif self.stage == RunStage.DISCOVER_INTAKE:
                    self._discover()
                    self._transition(
                        RunStage.INTAKE_ITEM if self._items else RunStage.INTAKE_BARRIER
                    )
                elif self.stage == RunStage.INTAKE_ITEM:
                    if not self._process_intake_item():
                        return self.view()
                    if self._item_index >= len(self._items):
                        self._set_status(
                            StageStatus.DONE,
                            {**self._intake_counts, "gates": tuple(self._gate_events)},
                        )
                        self._transition(RunStage.INTAKE_BARRIER)
                    else:
                        assert_transition(RunStage.INTAKE_ITEM, RunStage.INTAKE_ITEM)
                elif self.stage == RunStage.INTAKE_BARRIER:
                    if self.state_store.unfinished_publication() is not None:
                        raise RuntimeError("intake has an unfinished publication")
                    if self._intake_counts["failed"]:
                        raise RuntimeError("intake has mandatory failures")
                    pending = PhaseHandoffGate.pending(
                        intake_worked=self._intake_did_work,
                        counts=self._intake_counts,
                        note_paths=[
                            str(item["note_path"])
                            for item in self._item_results
                            if "note_path" in item
                        ],
                    )
                    if pending is not None:
                        self.pending = pending
                        self._set_status(StageStatus.BLOCKED, dict(self._intake_counts))
                        return self.view()
                    self._set_status(StageStatus.SKIPPED if not self._items else StageStatus.DONE)
                    self._transition(RunStage.CAPTURE_OBSIDIAN)
                elif self.stage == RunStage.CAPTURE_OBSIDIAN:
                    with self._session_factory(self.config) as session:
                        self._captured = self._capture(
                            session.pipeline, vault=self._resolve_vault()
                        )
                        # T63: each book's accumulated highlighted passages
                        # become explicit sibling highlights under page-level
                        # parents here, alongside ordinary vault-note capture -- tracked
                        # separately so the "every published note got
                        # captured" discrepancy check below still means what
                        # it says for photo pages, which no longer produce a
                        # 1:1 note capture by design.
                        self._captured_passages = capture_book_highlights(
                            session.pipeline, vault=self._resolve_vault()
                        )
                    total_captured = len(self._captured) + len(self._captured_passages)
                    self._set_status(
                        StageStatus.DONE if total_captured else StageStatus.SKIPPED,
                        {"captured": total_captured},
                    )
                    self._transition(RunStage.PROCESS_PENDING)
                elif self.stage == RunStage.PROCESS_PENDING:
                    with self._session_factory(self.config) as session:
                        fresh_outcomes = session.pipeline.process_pending(
                            limit=max(
                                len(self._captured) + len(self._captured_passages), 100
                            )
                        )
                    self._merge_processed_outcomes(fresh_outcomes)
                    self._envelopes_flagged = sum(
                        outcome.status == "review_pending" for outcome in self._processed
                    )
                    self._set_status(
                        StageStatus.DONE if self._processed else StageStatus.SKIPPED,
                        {"outcomes": [outcome.model_dump(mode="json") for outcome in self._processed]},
                    )
                    self._transition(RunStage.PROPOSAL_REVIEW)
                elif self.stage == RunStage.PROPOSAL_REVIEW:
                    with self._session_factory(self.config) as session:
                        pending = self._pending_proposal(session)
                    if pending is not None:
                        self.pending = pending
                        self._set_status(StageStatus.BLOCKED, {"envelope_id": pending.item_id})
                        return self.view()
                    self._set_status(StageStatus.SKIPPED if not self._envelopes_flagged else StageStatus.DONE)
                    self._transition(RunStage.DISPATCH_RETRY)
                elif self.stage == RunStage.DISPATCH_RETRY:
                    with self._session_factory(self.config) as session:
                        self._dispatch_outcomes = session.pipeline.retry_dispatches()
                        for outcome in self._dispatch_outcomes:
                            self._refresh_processed_outcome(
                                outcome, append_if_missing=False
                            )
                        failed_dispatches = [
                            dict(row)
                            for row in session.pipeline.store.rows("dispatches")
                            if row["status"] == "failed"
                        ]
                    # "The overall run cannot say complete while a required
                    # retry remains" means *this* run's retries. A dispatch that
                    # failed in an earlier run is reported as retryable, not
                    # raised on — otherwise one stale row fails every future run
                    # at its last stage, after all the work is already done.
                    mine = self._envelope_ids_this_run()
                    blocking = [
                        row for row in failed_dispatches
                        if str(row.get("envelope_id")) in mine
                    ]
                    self._stale_dispatch_failures = [
                        row for row in failed_dispatches
                        if str(row.get("envelope_id")) not in mine
                    ]
                    if blocking:
                        raise RuntimeError(
                            "dispatch retries remain failed: "
                            + ", ".join(
                                f"{row['envelope_id']}:{row['target']}" for row in blocking
                            )
                        )
                    self._set_status(
                        StageStatus.DONE if self._dispatch_outcomes else StageStatus.SKIPPED,
                        {"retried": len(self._dispatch_outcomes)},
                    )
                    unresolved = self._unresolved_processing_failures()
                    if unresolved:
                        statuses = sorted(
                            {
                                str(getattr(outcome, "status", "unknown"))
                                for outcome in unresolved
                            }
                        )
                        return self._fail(
                            RuntimeError(
                                f"{len(unresolved)} processing outcome(s) remain unresolved: "
                                + ", ".join(statuses)
                            ),
                            failed_from=RunStage.PROCESS_PENDING,
                        )
                    self._transition(RunStage.COMPLETE)
                    self._complete()
                    return self.view()
                else:
                    return self.view()
        except Exception as error:
            return self._fail(error)

    def submit_decision(self, decision: DecisionRequest) -> RunView:
        pending = self.pending
        if self.stage_status != StageStatus.BLOCKED or pending is None:
            raise IllegalDecisionError("the run is not waiting for a decision")
        if decision.run_id != self.run_id:
            raise IllegalDecisionError("decision belongs to a different run")
        if decision.item_id != pending.item_id or decision.gate != pending.gate:
            raise IllegalDecisionError("decision does not match the current item and gate")
        if decision.action not in pending.allowed_actions:
            raise IllegalDecisionError(f"action {decision.action!r} is not allowed")
        if not decision.resolver.strip():
            raise IllegalDecisionError("resolver cannot be blank")

        if pending.gate == "phase_handoff":
            self.pending = None
            if decision.action == "stop":
                self._set_status(StageStatus.DONE, {**dict(pending.payload), "action": "stop"})
                self._transition(RunStage.COMPLETE)
                self._complete()
                return self.view()
            self._set_status(StageStatus.DONE, {**dict(pending.payload), "action": "continue"})
            self._transition(RunStage.CAPTURE_OBSIDIAN)
            return self.advance()

        if pending.gate == "proposal":
            if pending.payload.get("envelope_level"):
                with self._session_factory(self.config) as session:
                    outcome = session.pipeline.resolve_review(
                        pending.item_id,
                        approved=decision.action == "approve",
                        resolver=decision.resolver,
                        note=decision.note,
                    )
                self._refresh_processed_outcome(outcome)
                self._review_counts[decision.action] += 1
                self._envelopes_resolved += 1
                self.pending = None
                self._set_status(StageStatus.RUNNING)
                return self.advance()
            edited = decision.payload.get("edited_proposal")
            # Caught here rather than as a pydantic ValidationError deeper in,
            # so Component 6 sees one decision-shaped error and the store is
            # never reached with a malformed decision.
            if decision.action == "edit" and edited is None:
                raise IllegalDecisionError(
                    "an edit decision requires an edited_proposal"
                )
            if decision.action != "edit" and edited is not None:
                raise IllegalDecisionError(
                    "edited_proposal is only valid when the action is edit"
                )
            proposal_decision = ProposalReviewDecision(
                proposal_id=str(pending.payload["proposal_id"]),
                action=cast(Any, decision.action),
                edited_proposal=cast(dict[str, Any] | None, edited),
                note=decision.note,
            )
            with self._session_factory(self.config) as session:
                outcome = session.pipeline.resolve_proposal_reviews(
                    str(pending.payload["envelope_id"]),
                    decisions=[proposal_decision],
                    resolver=decision.resolver,
                    note=decision.note,
                )
            self._refresh_processed_outcome(outcome)
            self._envelopes_resolved += outcome.status != "review_pending"
            self._review_counts[decision.action] += 1
            self.pending = None
            self._set_status(StageStatus.RUNNING)
            return self.advance()

        prepared = self._prepared
        if prepared is None:
            raise IllegalDecisionError("the prepared intake item is unavailable")
        gate = next((gate for gate in self._gates if gate.name == pending.gate), None)
        if gate is None:
            raise IllegalDecisionError(f"unknown gate: {pending.gate}")
        if decision.action == "retry":
            self._record_gate(prepared, pending.gate, "retrying")
            self.pending = None
            self._set_status(StageStatus.RUNNING, {"retrying": pending.gate})
            return self.advance()
        old_folder = prepared.source_path.parent
        gate.apply(prepared, decision)
        if pending.gate == "cleanup":
            # A per-occurrence action (Apply/Skip/Accept/Reject/Previous/Next)
            # leaves the gate still blocked -- only Continue actually finishes
            # it. Logging every intermediate action as "done" would falsely
            # tell diagnostics the gate completed after the first Apply
            # (component_8.md section 7.4).
            status = "done" if decision.action == "continue" else "cleanup_interaction"
            self._record_gate(prepared, gate.name, status, action=decision.action)
        else:
            self._record_gate(prepared, gate.name, "done", action=decision.action)
        if pending.gate == "book_metadata":
            # Use the path the rename actually produced rather than slugifying
            # the pre-confirmation title again — `correct` changes that title.
            new_folder = getattr(gate, "finalized_folder", None) or old_folder
            self._remap_book_folder(old_folder, new_folder)
        elif pending.gate == "content_approval" and decision.action in {"discard", "retake"}:
            self._finish_item(prepared, decision.action)
        elif pending.gate == "content_approval" and decision.action == "approve":
            # Cleanup state clears in _finish_item(), once this item is truly
            # done -- not here. Approve only marks the page "reviewed"; the
            # coordinator re-enters _process_intake_item() at least once more
            # before _publish_item() calls _finish_item(), and cleanup's own
            # pending()/overlay() must still recognize this item mid-flight.
            page = self._page_for(prepared)
            if page is not None:
                restored = Path(str(page.get("image_path") or prepared.source_path))
                self._items[self._item_index] = restored
        self.pending = None
        self._set_status(StageStatus.RUNNING)
        return self.advance()

    def retry(self) -> RunView:
        if self.stage != RunStage.FAILED or self._failed_from is None:
            raise IllegalStageTransition("retry is legal only after a failed stage")
        target = self._failed_from
        if target == RunStage.INTAKE_ITEM and self._intake_counts["failed"]:
            # `_fail()` counted this stage failure as a failed intake item so
            # the report would name it. A retry is an attempt to recover that
            # same item, so the count has to come back off first: INTAKE_BARRIER
            # refuses to pass while it is non-zero ("intake has mandatory
            # failures"), and since `_fail()` ends the run the moment it fires,
            # a retry is the *only* way that barrier is ever reached with a
            # non-zero count. Leaving it set made every intake retry fail a
            # second time even when the retried item succeeded, contradicting
            # T60's own recovery story ("You start Ollama, call `retry()`, and
            # it picks up the same photo"). If the item fails again, `_fail()`
            # simply counts it again.
            self._intake_counts["failed"] -= 1
        # The failure released the lock so a clean run could start instead.
        # Resuming this one takes it back, and the run stops being terminal.
        self.state_store.acquire_lock()
        self.terminal_result = None
        self._transition(target)
        self.last_error = None
        return self.advance()

    def _complete(self) -> None:
        self._set_status(StageStatus.DONE)
        self._finish("complete")

    def _photo_pages_published(self) -> int:
        return sum(
            1
            for item in self._item_results
            if item.get("outcome") == "published"
            and Path(str(item["source_path"])).suffix.lower() in IMAGE_EXTENSIONS
        )

    def _finish(self, terminal_result: str) -> None:
        """Record the run, then let go of the lock. Both terminal states."""

        self.terminal_result = terminal_result
        photo_pages_published = self._photo_pages_published()
        report_data = {
            "run_id": self.run_id,
            "terminal_result": self.terminal_result,
            "failed_from": (
                self._failed_from.value if self._failed_from is not None else None
            ),
            "last_error": (
                {
                    "stage": self.last_error.stage.value,
                    "message": self.last_error.message,
                    "retryable": self.last_error.retryable,
                }
                if self.last_error is not None
                else None
            ),
            "stages": [
                {
                    "stage": view.stage.value,
                    "status": view.status.value,
                    "detail": dict(view.detail),
                }
                for view in self._stage_views.values()
            ],
            "intake": {
                **self._intake_counts,
                "items": self._item_results,
                "gates": self._gate_events,
            },
            "vault_notes_written": [
                item["note_path"] for item in self._item_results if "note_path" in item
            ],
            "capture": [
                outcome.model_dump(mode="json") if hasattr(outcome, "model_dump") else outcome
                for outcome in (*self._captured, *self._captured_passages)
            ],
            "capture_counts": self._capture_counts(),
            "processing": [
                outcome.model_dump(mode="json") if hasattr(outcome, "model_dump") else outcome
                for outcome in self._processed
            ],
            "processing_counts": self._processing_counts(),
            "review": {
                **self._review_counts,
                "still_blocked": (
                    1
                    if self.pending is not None and self.pending.gate == "proposal"
                    else 0
                ),
            },
            "dispatch_counts": self._dispatch_counts(),
            "retryable_failures": [
                *(
                    outcome.model_dump(mode="json")
                    for outcome in self._processed
                    if getattr(outcome, "status", "")
                    in {"parse_failed", "extraction_failed", "quarantined"}
                ),
                # Dispatches this run did not touch. They are reported rather
                # than raised on, so one stale failure from weeks ago cannot
                # fail every future run at its last stage.
                *(
                    {
                        "stage": RunStage.DISPATCH_RETRY.value,
                        "envelope_id": row.get("envelope_id"),
                        "target": row.get("target"),
                        "detail": "dispatch failed in an earlier run",
                    }
                    for row in self._stale_dispatch_failures
                ),
            ],
            "discrepancies": [
                *(
                    # Photo-page notes are captured through their book's
                    # highlights document (T63), not one-to-one here -- the
                    # expectation below excludes them from this count.
                    ["fewer vault capture outcomes than non-photo notes published during intake"]
                    if len(self._captured)
                    < self._intake_counts["published"] - photo_pages_published
                    and RunStage.CAPTURE_OBSIDIAN in self._stage_views
                    else []
                ),
                *(
                    ["a published photo produced no captured highlight passages"]
                    if photo_pages_published
                    and not self._captured_passages
                    and RunStage.CAPTURE_OBSIDIAN in self._stage_views
                    else []
                ),
            ],
            "progress": self.view().progress.__dict__,
        }
        try:
            write_report(self.config.database_root / "reports", self.run_id, report_data)
        finally:
            # The lock is released even when the report cannot be written —
            # otherwise a failure caused by an unwritable disk strands the lock
            # and refuses every later run, which is the failure this releases.
            self.state_store.release_lock()

    def _envelope_ids_this_run(self) -> set[str]:
        return {
            str(getattr(outcome, "envelope_id", "") or "")
            for outcome in (*self._processed, *self._dispatch_outcomes)
        } - {""}

    @staticmethod
    def _outcome_key(outcome: Any) -> tuple[str, str, int | None]:
        envelope_id = str(getattr(outcome, "envelope_id", "") or "")
        return (
            envelope_id,
            str(getattr(outcome, "source_record_id", "") or ""),
            getattr(outcome, "highlight_index", None),
        )

    def _refresh_processed_outcome(
        self, outcome: Any, *, append_if_missing: bool = True
    ) -> None:
        """Replace a process-stage snapshot with its latest durable outcome."""

        key = self._outcome_key(outcome)
        for index, existing in enumerate(self._processed):
            existing_key = self._outcome_key(existing)
            same_item = (bool(key[0]) and key[0] == existing_key[0]) or (
                bool(key[1]) and key[1:] == existing_key[1:]
            )
            if not same_item:
                continue
            prior_targets = list(getattr(existing, "dispatched_targets", []))
            current_targets = list(getattr(outcome, "dispatched_targets", []))
            if hasattr(outcome, "model_copy"):
                updates: dict[str, Any] = {
                    "dispatched_targets": list(
                        dict.fromkeys((*prior_targets, *current_targets))
                    )
                }
                if (
                    getattr(outcome, "status", "") == "already_processed"
                    and getattr(existing, "status", "") == "processed"
                ):
                    updates["status"] = "processed"
                outcome = outcome.model_copy(
                    update=updates
                )
            self._processed[index] = outcome
            self._sync_processing_stage_detail()
            return
        if append_if_missing:
            self._processed.append(outcome)
            self._sync_processing_stage_detail()

    def _merge_processed_outcomes(self, outcomes: Sequence[Any]) -> None:
        for outcome in outcomes:
            source_id = str(getattr(outcome, "source_record_id", "") or "")
            highlight_index = getattr(outcome, "highlight_index", None)
            if highlight_index is not None:
                # A successful re-parse expands a document-scoped failure into
                # highlight-scoped outcomes; retire the obsolete failure row.
                self._processed = [
                    existing
                    for existing in self._processed
                    if not (
                        str(getattr(existing, "source_record_id", "") or "")
                        == source_id
                        and getattr(existing, "highlight_index", None) is None
                        and getattr(existing, "status", "")
                        in {"parse_failed", "quarantined"}
                    )
                ]
            self._refresh_processed_outcome(outcome)

    def _sync_processing_stage_detail(self) -> None:
        view = self._stage_views.get(RunStage.PROCESS_PENDING)
        if view is None:
            return
        self._stage_views[RunStage.PROCESS_PENDING] = StageView(
            RunStage.PROCESS_PENDING,
            view.status,
            {
                "outcomes": [
                    outcome.model_dump(mode="json") for outcome in self._processed
                ]
            },
        )

    def _unresolved_processing_failures(self) -> list[Any]:
        return [
            outcome
            for outcome in self._processed
            if getattr(outcome, "status", "")
            in {"parse_failed", "extraction_failed", "quarantined"}
        ]

    def _dispatch_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        seen: set[tuple[str, str]] = set()
        for outcome in (*self._processed, *self._dispatch_outcomes):
            for target in getattr(outcome, "dispatched_targets", []):
                identity = str(getattr(outcome, "envelope_id", "") or "")
                key = (identity, target)
                if identity and key in seen:
                    continue
                seen.add(key)
                counts[target] = counts.get(target, 0) + 1
        return counts

    def _capture_counts(self) -> dict[str, int]:
        combined = (*self._captured, *self._captured_passages)
        duplicates = sum(
            bool(getattr(outcome, "exact_duplicate", False))
            or bool(getattr(outcome, "normalized_duplicate", False))
            for outcome in combined
        )
        return {
            "total": len(combined),
            "new": len(combined) - duplicates,
            "duplicate": duplicates,
        }

    def _processing_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for outcome in self._processed:
            status = str(getattr(outcome, "status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        return counts
