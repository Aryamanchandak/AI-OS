"""Bridge from an approved ingestion envelope to the SQLite content store."""

from __future__ import annotations

from gateway.ingestion.content_store import ContentStore
from gateway.ingestion.models import IngestionEnvelope


class ContentConsumer:
    """`EnvelopeConsumer` implementation for the `sqlite` target."""

    target = "sqlite"

    def __init__(self, store: ContentStore) -> None:
        self.store = store

    def consume(self, envelope: IngestionEnvelope) -> str:
        self.store.project_envelope(envelope)
        return f"sqlite:{envelope.envelope_id}"
