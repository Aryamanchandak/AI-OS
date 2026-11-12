"""Sequential ingestion runner ("finding 1").

Composes the pieces that already exist and are individually tested --
`KGStore(strict=True)` preflight, `VectorStore`, `ContentStore`, the three
`EnvelopeConsumer`s, and one client for the system-wide GLC v5 gateway --
into one live, sequential run.

Decision 1 (PLAN_PART1.md): no CLI, one pipeline, sequential,
together-or-not-at-all. Steps run in order: preflight -> capture -> extract ->
project.

Decision 2: Neo4j down = refuse everything. Preflight runs first and raises
before any capture or processing happens -- no state changes on a failed
preflight.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, cast

from gateway.ingestion.config import IngestionConfig, load_root_env
from gateway.ingestion.consumers.content_consumer import ContentConsumer
from gateway.ingestion.consumers.kg_consumer import KGConsumer
from gateway.ingestion.consumers.vector_consumer import VectorConsumer
from gateway.ingestion.content_store import ContentStore
from gateway.ingestion.dispatch import EnvelopeConsumer
from gateway.ingestion.extraction.base import SemanticExtractor
from gateway.ingestion.extraction.gateway import GatewayExtractor
from gateway.ingestion.kg.kg_store import KGStore
from gateway.ingestion.models import CaptureOutcome, CaptureRequest, ProcessOutcome
from gateway.ingestion.parsing import GatewayTopicSegmenter, HeadingTopicSegmenter, TopicSegmenter
from gateway.ingestion.pipeline import UnifiedIngestionPipeline
from gateway.ingestion.sources.obsidian import capture_obsidian_vault
from gateway.ingestion.vector.vector_store import VectorStore
from gateway.ingestion.http_client import GatewayHTTPClient


class GatewayClient(Protocol):
    """The subset of the shared system gateway client required by ingestion."""

    def chat(
        self,
        prompt: str | None = None,
        *,
        messages: list[dict[str, Any]] | None = None,
        system: Any = None,
        profile: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        response_format: Any = None,
    ) -> dict[str, Any]: ...

    def embed(
        self,
        text: str,
        task_type: str = "retrieval_document",
        profile: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]: ...

    def resolve_chat_profile(self, profile: str) -> dict[str, Any]: ...


CaptureBatch = Callable[
    ["UnifiedIngestionPipeline"], list[CaptureOutcome]
]


def _shared_gateway_client() -> GatewayClient:
    """Create one profile based HTTP client for the Gateway LLM service."""
    return GatewayHTTPClient()


@dataclass
class RunReport:
    """Plain summary of one sequential run. Not a new persistence layer --
    every fact in here is already recorded by the ledger/content stores;
    this is just what the caller sees back."""

    captured: list[CaptureOutcome] = field(default_factory=list)
    processed: list[ProcessOutcome] = field(default_factory=list)
    effective_segmentation: dict[str, Any] = field(default_factory=dict)

    @property
    def captured_count(self) -> int:
        return len(self.captured)

    @property
    def dispatched_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for outcome in self.processed:
            for target in outcome.dispatched_targets:
                counts[target] = counts.get(target, 0) + 1
        return counts

    @property
    def review_pending_count(self) -> int:
        return sum(1 for outcome in self.processed if outcome.status == "review_pending")

    @property
    def empty_parse_count(self) -> int:
        """Documents the parse step found nothing to make a highlight out of."""
        return sum(1 for outcome in self.processed if outcome.status == "empty_parse")

    @property
    def failed_count(self) -> int:
        # `empty_parse` counts here too: a document that yielded no highlight
        # produced nothing, and a run summary that showed it nowhere would let
        # it vanish silently. `empty_parse_count` breaks it back out.
        return sum(
            1
            for outcome in self.processed
            if outcome.status
            in {"parse_failed", "extraction_failed", "quarantined", "empty_parse"}
        )


@dataclass
class IngestionSession:
    """The live production consumer stack for one bounded unit of work."""

    pipeline: UnifiedIngestionPipeline
    segmenter: TopicSegmenter
    gateway: GatewayClient

    def effective_segmentation(self) -> dict[str, Any]:
        reporter = getattr(self.segmenter, "effective_configuration", None)
        if callable(reporter):
            return cast(dict[str, Any], reporter())
        return {
            **self.pipeline.config.segmentation.report(),
            "resolved_provider": None,
            "resolved_model": None,
        }


@contextmanager
def ingestion_session(
    config: IngestionConfig,
    *,
    kg_store: KGStore | None = None,
    vector_store: VectorStore | None = None,
    content_store: ContentStore | None = None,
    extractor: SemanticExtractor | None = None,
    segmenter: TopicSegmenter | None = None,
    gateway_client: GatewayClient | None = None,
) -> Iterator[IngestionSession]:
    """Build the runner's stack once and expose it for bounded reuse."""

    load_root_env()
    owns_kg = kg_store is None
    owns_content = content_store is None
    kg = kg_store or KGStore(strict=True, expected_data_root=config.neo4j_path)
    try:
        kg.preflight()
        gateway = gateway_client or _shared_gateway_client()
        vector = vector_store or VectorStore(
            config.chroma_path, embedding_client=gateway
        )
        content = content_store or ContentStore(config.content_db_path)
        try:
            active_extractor = extractor or GatewayExtractor(chat_client=gateway)
            active_segmenter = segmenter or (
                GatewayTopicSegmenter(
                    chat_client=gateway,
                    config=config.segmentation,
                )
                if config.segmentation.mode == "gateway"
                else HeadingTopicSegmenter()
            )
            consumers: list[EnvelopeConsumer] = [
                KGConsumer(kg),
                VectorConsumer(
                    vector,
                    embedding_client=gateway,
                    chunk_config=config.embedding_chunks,
                ),
                ContentConsumer(content),
            ]
            with UnifiedIngestionPipeline(
                config,
                extractor=active_extractor,
                segmenter=active_segmenter,
                consumers=consumers,
            ) as pipeline:
                yield IngestionSession(pipeline, active_segmenter, gateway)
        finally:
            if owns_content:
                content.close()
    finally:
        if owns_kg:
            kg.close()


def run_ingestion(
    config: IngestionConfig,
    *,
    kg_store: KGStore | None = None,
    vector_store: VectorStore | None = None,
    content_store: ContentStore | None = None,
    extractor: SemanticExtractor | None = None,
    segmenter: TopicSegmenter | None = None,
    gateway_client: GatewayClient | None = None,
    capture_batch: CaptureBatch | None = None,
) -> RunReport:
    """Run one full sequential pass: preflight -> capture -> parse -> extract -> project.

    Stores, extractor, and gateway client may be injected for tests. Production
    construction creates exactly one Gateway HTTP client object and shares it
    across extraction, vector writes, and vector search. This is a client for
    the system-wide GLC v5 gateway, not a gateway owned by ingestion. Injected
    stores are the caller's responsibility to close.

    The default capture source is `capture_obsidian_vault`. A caller may inject
    one explicit `capture_batch` for bounded runs such as T5's single-document
    live smoke test; store/extractor composition remains identical.

    Capture and processing are two batch phases, not a per-item interleave
    (PLAN §2, the loading-dock model): each note is checked into capture on
    its own -- a note that fails (unreadable, malformed) is skipped and left
    for the next run, without blocking any other note. Only once every note
    has cleared capture does the whole cleared batch move to the next phase
    together (`process_pending`).

    Inside `process_pending` the unit of work is the highlight, not the note
    (T33): each note is parsed into highlights first, then every highlight
    still awaiting extraction -- including ones left over from earlier runs --
    is extracted in batches that may span notes. A failure is isolated to its
    own batch and its items stay pending for the next run; a failure after
    extraction (review, dispatch) is isolated to the single highlight, which is
    redone from its saved envelope rather than costing a second model call
    (decision 3, fail-fast delete-and-redo).
    """
    with ingestion_session(
        config,
        kg_store=kg_store,
        vector_store=vector_store,
        content_store=content_store,
        extractor=extractor,
        segmenter=segmenter,
        gateway_client=gateway_client,
    ) as session:
        capture = capture_batch or capture_obsidian_vault
        captured = capture(session.pipeline)
        processed = session.pipeline.process_pending(limit=max(len(captured), 100))
        return RunReport(
            captured=captured,
            processed=processed,
            effective_segmentation=session.effective_segmentation(),
        )


def run_document(
    config: IngestionConfig,
    document_path: Path,
    *,
    source_type: str = "markdown",
    metadata: dict[str, Any] | None = None,
    kg_store: KGStore | None = None,
    vector_store: VectorStore | None = None,
    content_store: ContentStore | None = None,
    extractor: SemanticExtractor | None = None,
    segmenter: TopicSegmenter | None = None,
    gateway_client: GatewayClient | None = None,
) -> RunReport:
    """Run the production pipeline against exactly one explicit document."""
    resolved = document_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Document not found: {resolved}")

    def capture_one(pipeline: UnifiedIngestionPipeline) -> list[CaptureOutcome]:
        return [
            pipeline.capture(
                CaptureRequest(
                    source_type=source_type,
                    origin=str(resolved),
                    content=resolved.read_bytes(),
                    metadata={
                        "note_title": resolved.stem,
                        **(metadata or {}),
                    },
                )
            )
        ]

    return run_ingestion(
        config,
        kg_store=kg_store,
        vector_store=vector_store,
        content_store=content_store,
        extractor=extractor,
        segmenter=segmenter,
        gateway_client=gateway_client,
        capture_batch=capture_one,
    )
