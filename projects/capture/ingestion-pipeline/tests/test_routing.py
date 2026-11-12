from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from ingestion.dispatch import Dispatcher
from ingestion.models import AccessPolicy, IngestionEnvelope
from ingestion.routing import DEFAULT_ALLOWED_CONSUMERS, resolve_targets


class RecordingStore:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def dispatch_status(
        self, envelope_id: str, target: str, extraction_version: str
    ) -> None:
        del envelope_id, target, extraction_version
        return None

    def record_dispatch(self, **values: Any) -> None:
        self.records.append(values)


class RecordingConsumer:
    def __init__(self, target: str) -> None:
        self.target = target
        self.calls: list[str] = []

    def consume(self, envelope: IngestionEnvelope) -> str:
        self.calls.append(envelope.envelope_id)
        return f"memory://{self.target}/{envelope.envelope_id}"


def envelope(
    *,
    source_type: str,
    allowed_consumers: list[str] | None = None,
) -> IngestionEnvelope:
    return IngestionEnvelope(
        envelope_id=f"envelope-{source_type}",
        source_record_id=f"source-{source_type}",
        canonical_record_id=f"source-{source_type}",
        source_type=source_type,
        origin=f"fixture://{source_type}",
        normalized_origin=f"fixture://{source_type}",
        captured_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        observed_at=None,
        raw_content_ref=f"bronze/{source_type}.raw",
        raw_content_hash=f"raw-{source_type}",
        normalized_content_hash=f"normalized-{source_type}",
        highlight_index=0,
        highlight_text=f"A {source_type} highlight.",
        highlight_start_char=0,
        highlight_end_char=20,
        version=1,
        access_policy=(
            AccessPolicy(allowed_consumers=allowed_consumers)
            if allowed_consumers is not None
            else AccessPolicy()
        ),
        extraction_version="routing-test-v1",
        confidence=1.0,
        review_status="not_required",
    )


def test_default_access_policy_allows_every_intended_store() -> None:
    assert tuple(AccessPolicy().allowed_consumers) == DEFAULT_ALLOWED_CONSUMERS


def test_resolver_returns_only_permitted_registered_targets() -> None:
    assert resolve_targets(
        allowed_consumers=["kg", "sqlite", "vector", "future_store"],
        registered_consumers=["vector", "kg", "unrelated"],
    ) == ("kg", "vector")


@pytest.mark.parametrize("source_type", ["email", "article", "future_format"])
def test_source_type_does_not_change_all_permitted_fan_out(source_type: str) -> None:
    consumers = [RecordingConsumer(target) for target in ("kg", "vector", "sqlite")]
    dispatcher = Dispatcher(RecordingStore(), consumers)

    results = dispatcher.dispatch(envelope(source_type=source_type))

    assert [result.target for result in results if result.status == "done"] == [
        "kg",
        "sqlite",
        "vector",
    ]
    assert all(consumer.calls == [f"envelope-{source_type}"] for consumer in consumers)


def test_access_policy_restriction_is_authoritative() -> None:
    consumers = [RecordingConsumer(target) for target in ("kg", "vector", "sqlite")]
    dispatcher = Dispatcher(RecordingStore(), consumers)

    results = dispatcher.dispatch(
        envelope(source_type="article", allowed_consumers=["sqlite"])
    )

    assert [(result.target, result.status) for result in results] == [
        ("kg", "skipped"),
        ("sqlite", "done"),
        ("vector", "skipped"),
    ]
    calls = {consumer.target: consumer.calls for consumer in consumers}
    assert calls == {
        "kg": [],
        "sqlite": ["envelope-article"],
        "vector": [],
    }
