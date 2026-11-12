from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
import re
from collections.abc import Sequence
from typing import Any, Literal, Protocol, cast
from urllib.parse import urlsplit

from gateway.ingestion.config import IngestionConfig
from gateway.ingestion.dispatch import Dispatcher, EnvelopeConsumer
from gateway.ingestion.extraction.base import (
    BatchSemanticExtractor,
    EmptySemanticExtractor,
    ExtractionError,
    ExtractionResult,
    HighlightExtractionInput,
    SemanticExtractor,
    extract_highlights,
)
from gateway.ingestion.models import (
    ClaimProposal,
    CaptureOutcome,
    CaptureRequest,
    IngestionEnvelope,
    ProposalReviewDecision,
    ProcessOutcome,
    ConceptProposal,
    RelationProposal,
    ReviewSignal,
)
from gateway.ingestion.normalization import MalformedSourceError, normalize_source
from gateway.ingestion.parsing import (
    HeadingTopicSegmenter,
    SegmentationFailure,
    TopicSegmenter,
    split_into_highlights,
)
from gateway.ingestion.review_policy import assess_review
from gateway.ingestion.store import IngestionStore

logger = logging.getLogger(__name__)

# Recorded on every parse so a future boundary change is identifiable in the
# ledger. Re-parsing under a new version is a deliberate delete-and-redo, not
# something this pipeline does on its own: highlight ids are derived from
# highlight indices, so silently re-splitting would orphan every projection.
PARSER_VERSION = "semantic_highlight_v2"


class HighlightCleanupGate(Protocol):
    """Component 8's seam: abbreviation/spelling suggestions for one highlight."""

    def suggestions(self, highlight_text: str) -> Sequence[str]: ...


class NoHighlightCleanup:
    """The gate T60 ships.

    A typed Obsidian highlight auto-ingests only when it has **no** cleanup
    suggestion and **no** review signal — both gates, as agreed. The second gate
    needs somewhere to live before Component 8 exists, so it lives here
    returning nothing: behaviour is unchanged, and Component 8 replaces one
    function rather than threading a new call through the pipeline.
    """

    def suggestions(self, highlight_text: str) -> tuple[str, ...]:
        del highlight_text
        return ()


class UnifiedIngestionPipeline:
    def __init__(
        self,
        config: IngestionConfig,
        *,
        extractor: SemanticExtractor | None = None,
        segmenter: TopicSegmenter | None = None,
        consumers: list[EnvelopeConsumer] | None = None,
        highlight_cleanup: HighlightCleanupGate | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.highlight_cleanup: HighlightCleanupGate = (
            highlight_cleanup or NoHighlightCleanup()
        )
        self.store = IngestionStore(config.ledger_path)
        self.extractor = extractor or EmptySemanticExtractor()
        # Deterministic segmentation is available only when the configuration
        # or caller explicitly selects it. A production/default gateway config
        # never silently falls back to headings.
        self.segmenter: TopicSegmenter | None = segmenter
        if self.segmenter is None and config.segmentation.mode == "deterministic":
            self.segmenter = HeadingTopicSegmenter()
        self.dispatcher = Dispatcher(self.store, consumers or [])

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "UnifiedIngestionPipeline":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _timestamp(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _source_extension(origin: str) -> str:
        """Return a safe final suffix from the source origin.

        Origins may be local paths or URLs. Only a short alphanumeric suffix
        can become part of a storage path; sources without one use ``.raw``.
        """
        suffix = Path(urlsplit(origin).path).suffix
        if not re.fullmatch(r"\.[A-Za-z0-9]{1,16}", suffix):
            return ".raw"
        return suffix.lower()

    def _raw_path(self, request: CaptureRequest, source_record_id: str) -> Path:
        return Path(self.config.raw_root) / (
            f"{source_record_id}{self._source_extension(request.origin)}"
        )

    @staticmethod
    def _write_immutable(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise RuntimeError(f"Immutable artifact collision: {path}")
            return

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o444)
            try:
                # A hard link publishes the fully-written inode atomically and,
                # unlike replace(), cannot overwrite an immutable destination.
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != content:
                    raise RuntimeError(f"Immutable artifact collision: {path}")
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def capture(self, request: CaptureRequest) -> CaptureOutcome:
        capture_id = str(uuid.uuid4())
        try:
            normalized = normalize_source(request.content, request.origin)
        except MalformedSourceError as exc:
            quarantined_request = request.model_dump(mode="python")
            if isinstance(quarantined_request.get("content"), bytes):
                quarantined_request["content"] = {
                    "encoding": "hex",
                    "value": quarantined_request["content"].hex(),
                }
            self.store.quarantine(quarantined_request, str(exc))
            raise

        captured_at = self._timestamp(request.captured_at)
        existing = self.store.find_by_raw_hash(normalized.raw_hash)
        if existing is not None:
            self.store.add_duplicate_capture(
                capture_id=capture_id,
                source_record_id=existing["id"],
                source_type=request.source_type,
                origin=request.origin,
                captured_at=captured_at,
                metadata=request.metadata,
            )
            return CaptureOutcome(
                source_record_id=existing["id"],
                canonical_record_id=existing["canonical_record_id"],
                capture_id=capture_id,
                raw_content_hash=normalized.raw_hash,
                normalized_content_hash=existing["normalized_hash"],
                version=int(existing["version"]),
                exact_duplicate=True,
                normalized_duplicate=existing["id"] != existing["canonical_record_id"],
                supersedes_record_id=existing["supersedes_record_id"],
                raw_content_ref=existing["raw_content_ref"],
            )

        normalized_match = self.store.find_by_normalized_hash(normalized.normalized_hash)
        latest = self.store.latest_for_origin(request.source_type, normalized.normalized_origin)
        if normalized_match is not None:
            version = int(normalized_match["version"])
            supersedes = None
        else:
            version = int(latest["version"]) + 1 if latest is not None else 1
            supersedes = str(latest["id"]) if latest is not None else None
        source_record_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"ingestion-source:{normalized.raw_hash}")
        )
        canonical_record_id = (
            str(normalized_match["canonical_record_id"])
            if normalized_match is not None
            else source_record_id
        )
        raw_path = self._raw_path(request, source_record_id)
        self._write_immutable(raw_path, normalized.raw_bytes)
        try:
            self.store.insert_source(
                source_record_id=source_record_id,
                raw_hash=normalized.raw_hash,
                normalized_hash=normalized.normalized_hash,
                canonical_record_id=canonical_record_id,
                source_type=request.source_type,
                origin=request.origin,
                normalized_origin=normalized.normalized_origin,
                captured_at=captured_at,
                observed_at=(
                    self._timestamp(request.observed_at) if request.observed_at is not None else None
                ),
                raw_content_ref=str(raw_path),
                version=version,
                supersedes_record_id=supersedes,
                metadata=request.metadata,
                extracted_metadata=normalized.extracted_metadata,
                access_policy=request.access_policy.model_dump(),
                boundary_origin=request.boundary_origin,
                user_selection=(
                    request.user_selection.model_dump()
                    if request.user_selection is not None
                    else (
                        {
                            "selections": [
                                selection.model_dump()
                                for selection in request.user_selections or []
                            ]
                        }
                        if request.user_selections
                        else None
                    )
                ),
                capture_id=capture_id,
                capture_source_type=request.source_type,
                normalized_duplicate=normalized_match is not None,
                mark_superseded=normalized_match is None,
            )
        except sqlite3.IntegrityError:
            # A concurrent capture may have registered the same hash after our
            # initial lookup. Bronze is never deleted; attach this capture to
            # the winning immutable record instead.
            concurrent = self.store.find_by_raw_hash(normalized.raw_hash)
            if concurrent is None:
                raise
            self.store.add_duplicate_capture(
                capture_id=capture_id,
                source_record_id=concurrent["id"],
                source_type=request.source_type,
                origin=request.origin,
                captured_at=captured_at,
                metadata=request.metadata,
            )
            return CaptureOutcome(
                source_record_id=concurrent["id"],
                canonical_record_id=concurrent["canonical_record_id"],
                capture_id=capture_id,
                raw_content_hash=normalized.raw_hash,
                normalized_content_hash=concurrent["normalized_hash"],
                version=int(concurrent["version"]),
                exact_duplicate=True,
                normalized_duplicate=concurrent["id"] != concurrent["canonical_record_id"],
                supersedes_record_id=concurrent["supersedes_record_id"],
                raw_content_ref=concurrent["raw_content_ref"],
            )
        return CaptureOutcome(
            source_record_id=source_record_id,
            canonical_record_id=canonical_record_id,
            capture_id=capture_id,
            raw_content_hash=normalized.raw_hash,
            normalized_content_hash=normalized.normalized_hash,
            version=version,
            exact_duplicate=False,
            normalized_duplicate=normalized_match is not None,
            supersedes_record_id=supersedes,
            raw_content_ref=str(raw_path),
        )

    def _write_envelope_artifact(self, envelope: IngestionEnvelope) -> Path:
        path = self.config.envelope_root / f"{envelope.envelope_id}.json"
        payload = (
            json.dumps(envelope.model_dump(mode="json"), sort_keys=True, indent=2)
            + "\n"
        )
        self._write_immutable(path, payload.encode("utf-8"))
        return Path(path)

    def _reverified_content(self, row: sqlite3.Row) -> str | None:
        """Re-read immutable bronze and confirm it still hashes as recorded.

        Returns None (after quarantining) when the file is gone, unreadable, or
        no longer matches — tamper must never reach extraction.
        """
        source_record_id = str(row["id"])
        raw_path = Path(str(row["raw_content_ref"]))
        try:
            normalized = normalize_source(raw_path.read_bytes(), str(row["origin"]))
        except (OSError, MalformedSourceError) as exc:
            self.store.quarantine({"source_record_id": source_record_id}, str(exc))
            return None
        if (
            normalized.raw_hash != row["raw_hash"]
            or normalized.normalized_hash != row["normalized_hash"]
        ):
            self.store.quarantine(
                {"source_record_id": source_record_id},
                "Immutable raw content no longer matches its recorded hashes",
            )
            return None
        return str(normalized.normalized_content)

    def parse_source(self, source_record_id: str) -> ProcessOutcome | None:
        """Split one captured document into stored highlights (the parse step).

        Returns None once the document has highlights waiting for extraction,
        or a terminal `ProcessOutcome` when it will never produce any. Parse
        output is persisted rather than recomputed on demand: the segmenter is
        model-backed, so re-splitting the same document may draw different
        boundaries, and every downstream id is derived from the index a
        highlight was given the first time.
        """
        row = self.store.get_source(source_record_id)
        if row is None:
            raise KeyError(f"Source record not found: {source_record_id}")
        content = self._reverified_content(row)
        if content is None:
            return ProcessOutcome(source_record_id=source_record_id, status="quarantined")

        selection = (
            json.loads(str(row["user_selection_json"]))
            if row["user_selection_json"]
            else None
        )
        selections = (
            selection.get("selections")
            if isinstance(selection, dict)
            and isinstance(selection.get("selections"), list)
            else None
        )
        try:
            highlights = split_into_highlights(
                content,
                segmenter=self.segmenter,
                config=self.config.segmentation,
                boundary_origin=cast(
                    Literal["document_segment", "user_selection"],
                    str(row["boundary_origin"]),
                ),
                supplied_context_text=(
                    selection.get("context_text") if selection is not None else None
                ),
                parent_start_char=(
                    selection.get("parent_start_char") if selection is not None else None
                ),
                parent_end_char=(
                    selection.get("parent_end_char") if selection is not None else None
                ),
                containing_sentence=(
                    selection.get("containing_sentence") if selection is not None else None
                ),
                supplied_selections=selections,
            )
        except SegmentationFailure as exc:
            self.store.record_parse_failure(
                source_record_id=source_record_id,
                failure_type=exc.code,
                error=str(exc),
                attempts=exc.attempts,
            )
            logger.warning(
                "Parse failed and remains pending for %s (%s): %s",
                source_record_id,
                exc.code,
                exc,
            )
            return ProcessOutcome(
                source_record_id=source_record_id,
                status="parse_failed",
            )
        self.store.save_parse(
            source_record_id=source_record_id,
            parser_version=PARSER_VERSION,
            normalized_content_hash=str(row["normalized_hash"]),
            highlights=[
                {
                    "index": highlight.index,
                    "text": highlight.text,
                    "context_text": highlight.context_text,
                    "heading": highlight.heading,
                    "start_char": highlight.start_char,
                    "end_char": highlight.end_char,
                    "start_word": highlight.start_word,
                    "end_word": highlight.end_word,
                    "segmentation": highlight.segmentation,
                }
                for highlight in highlights
            ],
        )
        if not highlights:
            logger.warning("Parse produced no highlights for %s", source_record_id)
            return ProcessOutcome(source_record_id=source_record_id, status="empty_parse")
        return None

    @staticmethod
    def _scope_proposal_ids(result: ExtractionResult, highlight_index: int) -> None:
        """Make proposal ids unique across the siblings of one document.

        An extractor sees one highlight and knows nothing about its position, so
        two highlights of the same document can hand back the same proposal id.
        Those ids are not envelope-local: they key the KG's edge and claim ids
        and the content store's claim primary key, so a collision would merge
        two highlights' beliefs into one row. The pipeline owns the
        document-to-highlight split, so it owns this scoping — one place,
        deterministic, and applied to every extractor alike.
        """
        for proposal in (
            *result.semantic.concepts,
            *result.semantic.claims,
            *result.semantic.relations,
        ):
            scoped = cast(ConceptProposal | ClaimProposal | RelationProposal, proposal)
            scoped.proposal_id = f"{scoped.proposal_id}:h{highlight_index}"

    def _build_envelope(
        self, row: sqlite3.Row, result: ExtractionResult
    ) -> IngestionEnvelope:
        source_record_id = str(row["source_record_id"])
        highlight_index = int(row["highlight_index"])
        highlight_text = str(row["text"])

        self._scope_proposal_ids(result, highlight_index)
        review_signals = assess_review(
            source_record_id=source_record_id,
            # The highlight is what this envelope asserts things about, so it is
            # also what evidence quotes are checked against — not the document.
            normalized_content=highlight_text,
            semantic=result.semantic,
            model_confidence=result.model_confidence,
            model_review_reasons=result.review_reasons,
            confidence_threshold=self.config.review_confidence_threshold,
        )
        metadata = json.loads(row["metadata_json"])
        if metadata.get("origin_kind") == "page_scanner":
            review_signals.append(
                ReviewSignal(
                    code="source_is_page_scanner",
                    scope="envelope",
                    detail="Highlights captured from scanned photos require review",
                )
            )
        elif self.highlight_cleanup.suggestions(highlight_text):
            # A typed highlight auto-ingests only with no cleanup suggestion and
            # no review signal. A photo-derived one already reaches review above.
            review_signals.append(
                ReviewSignal(
                    code="cleanup_suggestion_pending",
                    scope="envelope",
                    detail="The highlight has unresolved cleanup suggestions",
                )
            )
        review_status: Literal["pending", "not_required"] = (
            "pending" if review_signals else "not_required"
        )
        if review_status == "not_required":
            for concept in result.semantic.concepts:
                concept.status = "approved"
            for relation in result.semantic.relations:
                relation.status = "approved"
            for claim in result.semantic.claims:
                claim.status = "current"

        supersedes_record_id = row["supersedes_record_id"]
        segmentation = json.loads(str(row["segmentation_json"]))
        boundary_origin = cast(
            Literal["document_segment", "user_selection"],
            segmentation.get("boundary_origin", "document_segment"),
        )
        source_selection = (
            json.loads(str(row["user_selection_json"]))
            if row["user_selection_json"]
            else {}
        )
        # Multi-selection parents carry the applicable provenance on each
        # stored highlight.  A legacy single selection keeps it on the source.
        selection = (
            segmentation
            if segmentation.get("parent_source_ref") is not None
            else source_selection
        )
        return IngestionEnvelope(
            envelope_id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"ingestion-envelope:{source_record_id}:{highlight_index}"
                    f":{self.config.extraction_version}",
                )
            ),
            source_record_id=source_record_id,
            canonical_record_id=str(row["canonical_record_id"]),
            source_type=str(row["source_type"]),
            origin=str(row["origin"]),
            normalized_origin=str(row["normalized_origin"]),
            captured_at=row["captured_at"],
            observed_at=row["observed_at"],
            raw_content_ref=str(row["raw_content_ref"]),
            raw_content_hash=str(row["raw_hash"]),
            normalized_content_hash=str(row["normalized_hash"]),
            highlight_index=highlight_index,
            highlight_text=highlight_text,
            highlight_context_text=row["context_text"],
            highlight_start_char=int(row["start_char"]),
            highlight_end_char=int(row["end_char"]),
            highlight_boundary_origin=boundary_origin,
            highlight_parent_source_ref=selection.get("parent_source_ref"),
            highlight_parent_start_char=selection.get("parent_start_char"),
            highlight_parent_end_char=selection.get("parent_end_char"),
            highlight_containing_sentence=selection.get("containing_sentence"),
            version=int(row["version"]),
            supersedes_record_id=supersedes_record_id,
            supersedes_highlight_count=(
                self.store.highlight_count(str(supersedes_record_id))
                if supersedes_record_id
                else None
            ),
            source_status=cast(
                Literal["current", "superseded", "disputed"], str(row["source_status"])
            ),
            metadata=metadata,
            extracted_metadata=json.loads(row["extracted_metadata_json"]),
            access_policy=json.loads(row["access_policy_json"]),
            extraction_version=self.config.extraction_version,
            semantic=result.semantic,
            model_confidence=result.model_confidence,
            review_signals=review_signals,
            review_status=review_status,
        )

    def _project_highlight(
        self, row: sqlite3.Row, result: ExtractionResult
    ) -> ProcessOutcome:
        envelope = self._build_envelope(row, result)
        self._write_envelope_artifact(envelope)
        self.store.save_envelope(envelope)
        if envelope.review_signals:
            self.store.queue_review(envelope)
            return ProcessOutcome(
                source_record_id=envelope.source_record_id,
                highlight_index=envelope.highlight_index,
                envelope_id=envelope.envelope_id,
                status="review_pending",
            )
        results = self.dispatcher.dispatch(envelope)
        return ProcessOutcome(
            source_record_id=envelope.source_record_id,
            highlight_index=envelope.highlight_index,
            envelope_id=envelope.envelope_id,
            status="processed",
            dispatched_targets=[result.target for result in results if result.status == "done"],
        )

    @property
    def _extraction_batch_size(self) -> int:
        """How many highlights to put in one extraction call.

        Batching only saves anything when the extractor actually batches. An
        extractor that only implements `.extract()` is called once per highlight
        anyway, so batches of one keep each highlight's failure isolated instead
        of letting one bad highlight fail its neighbours for no saving.
        """
        if isinstance(self.extractor, BatchSemanticExtractor):
            return int(self.config.extraction_batch_size)
        return 1

    def _extract_pending(self, rows: list[sqlite3.Row]) -> list[ProcessOutcome]:
        """Extract and project a backlog of highlights, batched across documents.

        A batch is one model call, so it succeeds or fails as a unit: when a
        call fails, every highlight in it is reported `extraction_failed` and
        left pending for the next run. They are not retried one-by-one here —
        that would spend exactly the model calls the batching exists to avoid.
        A failure is confined to its own batch and never touches the rest of the
        backlog.
        """
        batch_size = self._extraction_batch_size
        outcomes: list[ProcessOutcome] = []
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            items = [
                HighlightExtractionInput(
                    batch_item_id=f"h{index}",
                    source_record_id=str(row["source_record_id"]),
                    highlight_index=int(row["highlight_index"]),
                    highlight_text=str(row["text"]),
                    context_text=row["context_text"],
                    metadata={
                        **json.loads(row["extracted_metadata_json"]),
                        **json.loads(row["metadata_json"]),
                    },
                )
                for index, row in enumerate(batch)
            ]
            try:
                results = extract_highlights(self.extractor, items)
            except ExtractionError as exc:
                logger.warning(
                    "Extraction failed for a batch of %d highlight(s): %s",
                    len(batch),
                    exc,
                )
                outcomes.extend(
                    ProcessOutcome(
                        source_record_id=item.source_record_id,
                        highlight_index=item.highlight_index,
                        status="extraction_failed",
                    )
                    for item in items
                )
                continue
            for item, row in zip(items, batch):
                outcomes.append(self._project_highlight(row, results[item.batch_item_id]))
        return outcomes

    def process_source(self, source_record_id: str) -> list[ProcessOutcome]:
        """Parse, extract, and dispatch one document — one outcome per highlight.

        A document maps to N envelopes, so this returns a list. Already-built
        envelopes are re-dispatched (a no-op once every target is `done`), and
        only highlights without an envelope at this extraction version are sent
        to the extractor.
        """
        row = self.store.get_source(source_record_id)
        if row is None:
            raise KeyError(f"Source record not found: {source_record_id}")
        if row["id"] != row["canonical_record_id"]:
            return [
                ProcessOutcome(source_record_id=source_record_id, status="already_processed")
            ]

        if self.store.highlight_count(source_record_id) is None:
            failure = self.parse_source(source_record_id)
            if failure is not None:
                return [failure]

        outcomes = [
            self._redispatch(envelope)
            for envelope in self.store.get_envelopes_for_source(
                source_record_id, self.config.extraction_version
            )
        ]
        outcomes.extend(
            self._extract_pending(
                self.store.highlights_pending_extraction(
                    self.config.extraction_version, source_record_id=source_record_id
                )
            )
        )
        return outcomes

    def _redispatch(self, envelope: IngestionEnvelope) -> ProcessOutcome:
        results = self.dispatcher.dispatch(envelope)
        return ProcessOutcome(
            source_record_id=envelope.source_record_id,
            highlight_index=envelope.highlight_index,
            envelope_id=envelope.envelope_id,
            status=(
                "review_pending"
                if envelope.review_status == "pending"
                else "already_processed"
            ),
            dispatched_targets=[result.target for result in results if result.status == "done"],
        )

    def process_pending(self, limit: int = 100) -> list[ProcessOutcome]:
        """Parse every unparsed document, then extract the whole backlog.

        Two phases, deliberately. Parsing is per document and cheap. Extraction
        then pools every highlight still waiting — across all documents, not
        just the ones parsed in this run — so one batch can cover several
        documents and a run costs `ceil(pending_highlights / batch_size)` model
        calls rather than one per highlight.

        `limit` bounds *documents* entering the parse phase, so one very long
        note cannot starve the rest of the run.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        outcomes: list[ProcessOutcome] = []
        for row in self.store.sources_pending_parse(limit):
            failure = self.parse_source(str(row["id"]))
            if failure is not None:
                outcomes.append(failure)
        outcomes.extend(
            self._extract_pending(
                self.store.highlights_pending_extraction(self.config.extraction_version)
            )
        )
        return outcomes

    def resolve_review(
        self,
        envelope_id: str,
        *,
        approved: bool,
        resolver: str,
        note: str = "",
    ) -> ProcessOutcome:
        if not resolver.strip():
            raise ValueError("resolver cannot be blank")
        envelope = self.store.resolve_review(
            envelope_id, approved=approved, resolver=resolver, note=note
        )
        results = self.dispatcher.dispatch(envelope) if approved else []
        return ProcessOutcome(
            source_record_id=envelope.source_record_id,
            highlight_index=envelope.highlight_index,
            envelope_id=envelope.envelope_id,
            status="processed" if approved else "rejected",
            dispatched_targets=[result.target for result in results if result.status == "done"],
        )

    def resolve_proposal_reviews(
        self,
        envelope_id: str,
        *,
        decisions: list[ProposalReviewDecision],
        resolver: str,
        note: str = "",
    ) -> ProcessOutcome:
        if not resolver.strip():
            raise ValueError("resolver cannot be blank")
        envelope = self.store.resolve_proposal_reviews(
            envelope_id,
            decisions=decisions,
            resolver=resolver,
            note=note,
        )
        results = (
            self.dispatcher.dispatch(envelope)
            if envelope.review_status == "approved"
            else []
        )
        if envelope.review_status == "approved":
            status: Literal["processed", "review_pending", "rejected"] = "processed"
        elif envelope.review_status == "pending":
            status = "review_pending"
        else:
            status = "rejected"
        return ProcessOutcome(
            source_record_id=envelope.source_record_id,
            highlight_index=envelope.highlight_index,
            envelope_id=envelope.envelope_id,
            status=status,
            dispatched_targets=[
                result.target for result in results if result.status == "done"
            ],
        )

    def retry_dispatches(self) -> list[ProcessOutcome]:
        outcomes: list[ProcessOutcome] = []
        for envelope in self.store.pending_approved_envelopes():
            results = self.dispatcher.dispatch(envelope)
            outcomes.append(
                ProcessOutcome(
                    source_record_id=envelope.source_record_id,
                    highlight_index=envelope.highlight_index,
                    envelope_id=envelope.envelope_id,
                    status="already_processed",
                    dispatched_targets=[result.target for result in results if result.status == "done"],
                )
            )
        return outcomes
