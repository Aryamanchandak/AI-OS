from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast

from unified_ingestion.config import IngestionConfig
from unified_ingestion.dispatch import Dispatcher, EnvelopeConsumer
from unified_ingestion.extraction import EmptySemanticExtractor, SemanticExtractor
from unified_ingestion.models import (
    CaptureOutcome,
    CaptureRequest,
    IngestionEnvelope,
    ProcessOutcome,
)
from unified_ingestion.normalization import MalformedSourceError, normalize_source
from unified_ingestion.store import IngestionStore


class UnifiedIngestionPipeline:
    def __init__(
        self,
        config: IngestionConfig,
        *,
        extractor: SemanticExtractor | None = None,
        consumers: list[EnvelopeConsumer] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.store = IngestionStore(config.ledger_path)
        self.extractor = extractor or EmptySemanticExtractor()
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

    def _raw_path(self, request: CaptureRequest, source_record_id: str) -> Path:
        captured_at = request.captured_at
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        day = captured_at.astimezone(timezone.utc).date().isoformat()
        return self.config.raw_root / day / request.source_type / f"{source_record_id}.raw"

    @staticmethod
    def _write_immutable(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise RuntimeError(f"Immutable raw path collision: {path}")
            return
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o444)

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
            if request.legacy_source_id:
                self.store.map_legacy_reference(request.legacy_source_id, existing["id"])
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
            uuid.uuid5(uuid.NAMESPACE_URL, f"unified-source:{normalized.raw_hash}")
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
            if request.legacy_source_id:
                self.store.map_legacy_reference(request.legacy_source_id, concurrent["id"])
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
        if request.legacy_source_id:
            self.store.map_legacy_reference(request.legacy_source_id, source_record_id)
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
        self.config.envelope_root.mkdir(parents=True, exist_ok=True)
        path = self.config.envelope_root / f"{envelope.envelope_id}.json"
        temporary = self.config.envelope_root / f".{envelope.envelope_id}.tmp"
        temporary.write_text(
            json.dumps(envelope.model_dump(mode="json"), sort_keys=True, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def process_source(self, source_record_id: str) -> ProcessOutcome:
        existing_envelope = self.store.get_envelope_for_source(
            source_record_id, self.config.extraction_version
        )
        if existing_envelope is not None:
            results = self.dispatcher.dispatch(existing_envelope)
            return ProcessOutcome(
                source_record_id=source_record_id,
                envelope_id=existing_envelope.envelope_id,
                status=(
                    "review_pending"
                    if existing_envelope.review_status == "pending"
                    else "already_processed"
                ),
                dispatched_targets=[result.target for result in results if result.status == "done"],
            )
        row = self.store.get_source(source_record_id)
        if row is None:
            raise KeyError(f"Source record not found: {source_record_id}")
        if row["id"] != row["canonical_record_id"]:
            return ProcessOutcome(source_record_id=source_record_id, status="already_processed")
        raw_path = Path(str(row["raw_content_ref"]))
        try:
            normalized = normalize_source(raw_path.read_bytes(), str(row["origin"]))
        except (OSError, MalformedSourceError) as exc:
            self.store.quarantine({"source_record_id": source_record_id}, str(exc))
            return ProcessOutcome(source_record_id=source_record_id, status="quarantined")
        if normalized.raw_hash != row["raw_hash"] or normalized.normalized_hash != row["normalized_hash"]:
            error = "Immutable raw content no longer matches its recorded hashes"
            self.store.quarantine({"source_record_id": source_record_id}, error)
            return ProcessOutcome(source_record_id=source_record_id, status="quarantined")
        metadata = {
            **json.loads(row["extracted_metadata_json"]),
            **json.loads(row["metadata_json"]),
        }
        extraction = self.extractor.extract(
            source_record_id=source_record_id,
            normalized_content=normalized.normalized_content,
            metadata=metadata,
        )
        reasons = list(extraction.review_reasons)
        if any(concept.aliases for concept in extraction.semantic.concepts) or any(
            relation.predicate.casefold() in {"same_as", "alias_of", "equivalent_to"}
            for relation in extraction.semantic.relations
        ):
            reasons.append("alias_or_identity_proposal")
        if extraction.semantic.source_quality_signals:
            reasons.append("source_quality_signal")
        missing_claim_evidence = any(
            not claim.evidence
            or any(
                ref.normalized_char_start is None or ref.normalized_char_end is None
                for ref in claim.evidence
            )
            for claim in extraction.semantic.claims
        )
        missing_relation_evidence = any(
            not relation.evidence
            or any(
                ref.normalized_char_start is None or ref.normalized_char_end is None
                for ref in relation.evidence
            )
            for relation in extraction.semantic.relations
        )
        if missing_claim_evidence or missing_relation_evidence:
            reasons.append("missing_or_unresolved_evidence")
        proposal_confidences = [
            *(proposal.confidence for proposal in extraction.semantic.concepts),
            *(proposal.confidence for proposal in extraction.semantic.claims),
            *(proposal.confidence for proposal in extraction.semantic.relations),
        ]
        if extraction.confidence < self.config.review_confidence_threshold:
            reasons.append("overall_confidence_below_threshold")
        if any(value < self.config.review_confidence_threshold for value in proposal_confidences):
            reasons.append("proposal_confidence_below_threshold")
        review_status: Literal["pending", "not_required"] = (
            "pending" if reasons else "not_required"
        )
        if review_status == "not_required":
            for concept in extraction.semantic.concepts:
                concept.status = "approved"
            for relation in extraction.semantic.relations:
                relation.status = "approved"
            for claim in extraction.semantic.claims:
                claim.status = "current"
        envelope_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"ingestion-envelope:{source_record_id}:{self.config.extraction_version}",
            )
        )
        envelope = IngestionEnvelope(
            envelope_id=envelope_id,
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
            version=int(row["version"]),
            supersedes_record_id=row["supersedes_record_id"],
            source_status=cast(
                Literal["current", "superseded", "disputed"], str(row["source_status"])
            ),
            metadata=json.loads(row["metadata_json"]),
            extracted_metadata=json.loads(row["extracted_metadata_json"]),
            access_policy=json.loads(row["access_policy_json"]),
            extraction_version=self.config.extraction_version,
            semantic=extraction.semantic,
            confidence=extraction.confidence,
            review_status=review_status,
        )
        self._write_envelope_artifact(envelope)
        self.store.save_envelope(envelope)
        if reasons:
            self.store.queue_review(envelope_id, sorted(set(reasons)))
            return ProcessOutcome(
                source_record_id=source_record_id,
                envelope_id=envelope_id,
                status="review_pending",
            )
        results = self.dispatcher.dispatch(envelope)
        return ProcessOutcome(
            source_record_id=source_record_id,
            envelope_id=envelope_id,
            status="processed",
            dispatched_targets=[result.target for result in results if result.status == "done"],
        )

    def process_pending(self, limit: int = 100) -> list[ProcessOutcome]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return [
            self.process_source(str(row["id"]))
            for row in self.store.pending_sources(self.config.extraction_version, limit)
        ]

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
        self._write_envelope_artifact(envelope)
        results = self.dispatcher.dispatch(envelope) if approved else []
        return ProcessOutcome(
            source_record_id=envelope.source_record_id,
            envelope_id=envelope.envelope_id,
            status="processed" if approved else "rejected",
            dispatched_targets=[result.target for result in results if result.status == "done"],
        )

    def retry_dispatches(self) -> list[ProcessOutcome]:
        outcomes: list[ProcessOutcome] = []
        for envelope in self.store.pending_approved_envelopes():
            results = self.dispatcher.dispatch(envelope)
            outcomes.append(
                ProcessOutcome(
                    source_record_id=envelope.source_record_id,
                    envelope_id=envelope.envelope_id,
                    status="already_processed",
                    dispatched_targets=[result.target for result in results if result.status == "done"],
                )
            )
        return outcomes
