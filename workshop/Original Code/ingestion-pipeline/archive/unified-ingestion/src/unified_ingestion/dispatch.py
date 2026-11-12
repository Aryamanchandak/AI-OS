from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from unified_ingestion.models import DispatchResult, IngestionEnvelope
from unified_ingestion.store import IngestionStore


class EnvelopeConsumer(Protocol):
    target: str

    def consume(self, envelope: IngestionEnvelope) -> str | None: ...


class JsonHandoffConsumer:
    """Durable, idempotent handoff for a final-store consumer.

    The artifact contains the same validated envelope for every target. KG and
    vector consumers remain responsible for their optimized derived writes.
    """

    def __init__(self, target: str, root: Path) -> None:
        if target not in {"kg", "vector"}:
            raise ValueError("JsonHandoffConsumer target must be kg or vector")
        self.target = target
        self.root = root

    def consume(self, envelope: IngestionEnvelope) -> str:
        directory = self.root / self.target
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{envelope.envelope_id}.json"
        temporary = directory / f".{envelope.envelope_id}.tmp"
        temporary.write_text(
            json.dumps(
                {
                    "target": self.target,
                    "envelope": envelope.model_dump(mode="json"),
                    "provenance": {
                        "source_record_id": envelope.source_record_id,
                        "raw_content_ref": envelope.raw_content_ref,
                        "raw_content_hash": envelope.raw_content_hash,
                        "normalized_content_hash": envelope.normalized_content_hash,
                        "version": envelope.version,
                        "supersedes_record_id": envelope.supersedes_record_id,
                    },
                },
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
        return str(path)


class Dispatcher:
    def __init__(self, store: IngestionStore, consumers: list[EnvelopeConsumer]) -> None:
        targets = [consumer.target for consumer in consumers]
        if len(targets) != len(set(targets)):
            raise ValueError("Only one consumer may be registered per target")
        self._store = store
        self._consumers = {consumer.target: consumer for consumer in consumers}

    def dispatch(self, envelope: IngestionEnvelope) -> list[DispatchResult]:
        if envelope.review_status not in {"not_required", "approved"}:
            return []
        results: list[DispatchResult] = []
        for target, consumer in sorted(self._consumers.items()):
            if target not in envelope.access_policy.allowed_consumers:
                results.append(DispatchResult(target=target, status="skipped"))
                continue
            existing = self._store.dispatch_status(
                envelope.envelope_id, target, envelope.extraction_version
            )
            if existing is not None and existing["status"] == "done":
                results.append(
                    DispatchResult(
                        target=target,
                        status="skipped",
                        artifact_ref=existing["artifact_ref"],
                    )
                )
                continue
            try:
                artifact_ref = consumer.consume(envelope)
                self._store.record_dispatch(
                    envelope_id=envelope.envelope_id,
                    target=target,
                    extraction_version=envelope.extraction_version,
                    status="done",
                    artifact_ref=artifact_ref,
                )
                results.append(
                    DispatchResult(target=target, status="done", artifact_ref=artifact_ref)
                )
            except Exception as exc:
                self._store.record_dispatch(
                    envelope_id=envelope.envelope_id,
                    target=target,
                    extraction_version=envelope.extraction_version,
                    status="failed",
                    error=str(exc),
                )
                results.append(DispatchResult(target=target, status="failed", error=str(exc)))
        return results
