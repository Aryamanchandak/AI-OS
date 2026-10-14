from __future__ import annotations

from typing import Protocol

from ingestion.models import DispatchResult, IngestionEnvelope
from ingestion.routing import resolve_targets
from ingestion.store import IngestionStore


class EnvelopeConsumer(Protocol):
    target: str

    def consume(self, envelope: IngestionEnvelope) -> str | None: ...


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
        permitted_targets = set(
            resolve_targets(
                allowed_consumers=envelope.access_policy.allowed_consumers,
                registered_consumers=self._consumers,
            )
        )
        results: list[DispatchResult] = []
        for target, consumer in sorted(self._consumers.items()):
            if target not in permitted_targets:
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
