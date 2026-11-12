"""Tests for the sequential ingestion runner ("finding 1", PLAN §2).

Offline only: a duck-typed fake KG store (isolates preflight-gating and
composition from KGStore's real Cypher, already covered by
test_kg_preflight.py / test_kg_consumer.py), a fake Chroma client (mirrors
test_vector_store.py's FakeClient), and a fake extractor (mirrors
test_pipeline.py's FixtureExtractor). The separate real
Neo4j/Chroma/gateway T5 path lives in ``scripts/live_smoke.py`` so this suite
remains deterministic and offline (PLAN §4).
"""

from __future__ import annotations

from importlib.util import find_spec
import inspect
from pathlib import Path

import pytest

import ingestion.runner as runner_module
from ingestion.config import IngestionConfig
from ingestion.content_store import ContentStore
from ingestion.extraction.base import ExtractionError, ExtractionResult
from ingestion.extraction.gateway import ChatClient
from ingestion.kg.errors import KGUnavailableError
from ingestion.kg.models import KGNode
from ingestion.models import ClaimProposal, ConceptProposal, EvidenceRef, SemanticExtraction
from ingestion.parsing import HeadingTopicSegmenter
from ingestion.runner import run_document, run_ingestion
from ingestion.sources.obsidian import capture_obsidian_vault as _real_capture_obsidian_vault
from ingestion.vector.vector_store import EMBEDDING_DIMENSION, VectorStore


class FakeKGStore:
    """Duck-typed KGStore stand-in. Proves the runner wires KGConsumer to
    whatever store it's given and gates the whole run on `.preflight()` --
    not that KGConsumer's Cypher mapping is correct (test_kg_consumer.py) or
    that KGStore's real preflight checks work (test_kg_preflight.py)."""

    def __init__(self, *, fail_preflight: bool = False) -> None:
        self.fail_preflight = fail_preflight
        self.preflight_called = False
        self.closed = False
        self.resolved: list[str] = []
        self.claims: list = []
        self.edges: list = []

    def preflight(self) -> None:
        self.preflight_called = True
        if self.fail_preflight:
            raise KGUnavailableError("fake preflight failure")

    def resolve_or_create_node(
        self, label, *, domain="general", node_id=None, external_ids=None, fields=None, highlight_id=None
    ):
        self.resolved.append(label)
        return KGNode(id=f"node:{label}", canonical_name=label, domain=domain), [], True

    def submit_identity_proposal(self, proposal) -> None:
        pass

    def upsert_edge(self, edge) -> None:
        self.edges.append(edge)

    def upsert_edge_batch(self, edges) -> None:
        self.edges.extend(edges)

    def upsert_claim(self, claim) -> None:
        self.claims.append(claim)

    def purge_contributions(self, highlight_id) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FixtureExtractor:
    """Deterministic extractor: one concept + one claim per source, high
    enough confidence to skip review-gating. Fails (ExtractionError) for any
    source whose content contains the marker, so failure isolation can be
    exercised without depending on generated source_record_ids."""

    def __init__(self, *, fail_marker: str | None = None) -> None:
        self.fail_marker = fail_marker
        self.calls = 0

    def extract(self, *, source_record_id, normalized_content, metadata) -> ExtractionResult:
        self.calls += 1
        if self.fail_marker and self.fail_marker in normalized_content:
            raise ExtractionError("forced failure")
        quote = normalized_content.strip()
        evidence = [
            EvidenceRef(
                source_record_id=source_record_id,
                quote=quote,
                normalized_char_start=0,
                normalized_char_end=len(quote),
            )
        ]
        return ExtractionResult(
            semantic=SemanticExtraction(
                concepts=[
                    ConceptProposal(
                        proposal_id=f"concept-{source_record_id}",
                        label="Duration",
                        domain="finance",
                        confidence=0.95,
                        source_record_id=source_record_id,
                        evidence=evidence,
                    )
                ],
                claims=[
                    ClaimProposal(
                        proposal_id=f"claim-{source_record_id}",
                        text="Duration measures rate sensitivity.",
                        concept_labels=["Duration"],
                        confidence=0.95,
                        source_record_id=source_record_id,
                        evidence=evidence,
                    )
                ],
            ),
            confidence=0.95,
            review_reasons=[],
        )


class FakeGatewayClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def chat(self, *args, **kwargs):
        raise AssertionError("chat was not expected because this test injects an extractor")

    def embed(self, text, task_type="retrieval_document", provider=None):
        self.calls.append(text)
        return {
            "provider": "ollama",
            "model": "nomic-embed-text",
            "dim": EMBEDDING_DIMENSION,
            "embedding": [0.0] * EMBEDDING_DIMENSION,
        }

    def resolve_chat_profile(self, profile):
        return {
            "profile": profile,
            "provider": "phi4-local",
            "model": "phi4:14b-q4_K_M",
        }


class FakeChromaCollection:
    def __init__(self, name: str, metadata: dict | None = None) -> None:
        self.name = name
        self.metadata = metadata or {}
        self.upserts: list[dict] = []

    def upsert(self, **kwargs) -> None:
        self.upserts.append(kwargs)

    def delete(self, **kwargs) -> None:
        pass

    def get(self, **kwargs):
        return {"ids": [], "metadatas": [], "documents": []}


class FakeChromaClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeChromaCollection] = {}

    def list_collections(self):
        return list(self.collections.values())

    def get_collection(self, *, name: str):
        return self.collections[name]

    def get_or_create_collection(self, *, name: str, metadata: dict):
        return self.collections.setdefault(name, FakeChromaCollection(name, metadata))


def _make_vault(tmp_path: Path, notes: dict[str, str]) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    for name, content in notes.items():
        (vault / name).write_text(content, encoding="utf-8")
    return vault


def _config(tmp_path: Path) -> IngestionConfig:
    return IngestionConfig(database_root=tmp_path / "Database")


def _patch_capture(monkeypatch: pytest.MonkeyPatch, vault: Path) -> None:
    def _capture(pipeline):
        return _real_capture_obsidian_vault(pipeline, vault=vault)

    monkeypatch.setattr(runner_module, "capture_obsidian_vault", _capture)


def test_preflight_failure_stops_before_any_capture_or_state_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _make_vault(tmp_path, {"note.md": "Duration measures interest rate sensitivity."})
    _patch_capture(monkeypatch, vault)
    config = _config(tmp_path)
    kg = FakeKGStore(fail_preflight=True)

    with pytest.raises(KGUnavailableError):
        run_ingestion(
            config,
            kg_store=kg,
            vector_store=VectorStore(config.chroma_path, client=FakeChromaClient()),
            content_store=ContentStore(config.content_db_path),
            extractor=FixtureExtractor(),
        )

    assert kg.preflight_called
    assert not config.raw_root.exists()
    assert not config.envelope_root.exists()
    assert not config.ledger_path.exists()


def test_default_construction_reaches_real_preflight_and_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default construction reaches preflight without touching a live graph."""
    vault = _make_vault(tmp_path, {"note.md": "Duration measures interest rate sensitivity."})
    _patch_capture(monkeypatch, vault)
    config = _config(tmp_path)
    kg = FakeKGStore(fail_preflight=True)
    constructor_kwargs = {}

    def fake_store(**kwargs):
        constructor_kwargs.update(kwargs)
        return kg

    monkeypatch.setattr(runner_module, "KGStore", fake_store)

    with pytest.raises(KGUnavailableError):
        run_ingestion(config)

    assert kg.preflight_called
    assert constructor_kwargs == {
        "strict": True,
        "expected_data_root": config.neo4j_path,
    }
    assert not config.raw_root.exists()
    assert not config.envelope_root.exists()
    assert not config.ledger_path.exists()


def test_llm_gateway_client_is_a_real_installed_dependency() -> None:
    """merged-ingestion depends on llm_gateway as a real, non-editable package
    (see pyproject.toml [tool.uv.sources]), not the old pytest-only
    pythonpath hack. Construct it exactly the way `_shared_gateway_client`
    does, so a packaging regression -- e.g. reverting to an editable install,
    which silently breaks on this machine because uv chflags-hides the
    resulting .pth file and macOS's site.py skips hidden .pth files -- fails
    this test instead of only surfacing when someone runs the pipeline for
    real."""
    client = runner_module._shared_gateway_client()
    assert client.base_url


@pytest.mark.parametrize("protocol", [runner_module.GatewayClient, ChatClient])
def test_gateway_protocols_declare_multimodal_messages(protocol: type) -> None:
    parameter = inspect.signature(protocol.chat).parameters["messages"]
    assert parameter.default is None


def test_live_store_drivers_are_standard_runtime_dependencies() -> None:
    assert find_spec("neo4j") is not None
    assert find_spec("chromadb") is not None


def test_end_to_end_dispatches_to_all_three_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = FakeGatewayClient()
    vault = _make_vault(tmp_path, {"note.md": "Duration measures interest rate sensitivity."})
    _patch_capture(monkeypatch, vault)
    config = _config(tmp_path)
    kg = FakeKGStore()
    chroma = FakeChromaClient()
    content_db_path = config.content_db_path

    report = run_ingestion(
        config,
        kg_store=kg,
        vector_store=VectorStore(config.chroma_path, client=chroma),
        content_store=ContentStore(content_db_path),
        extractor=FixtureExtractor(),
        gateway_client=gateway,
    )

    assert kg.preflight_called
    assert kg.closed is False  # injected store: caller's lifecycle, not ours
    assert report.captured_count == 1
    assert len(report.processed) == 1
    assert report.processed[0].status == "processed"
    assert report.dispatched_counts == {"kg": 1, "vector": 1, "sqlite": 1}
    assert report.review_pending_count == 0
    assert report.failed_count == 0

    # KG got the concept.
    assert "Duration" in kg.resolved
    assert len(kg.claims) == 1

    # Chroma got at least one chunk, embedded via the (patched) gateway client.
    collection = chroma.collections["knowledge"]
    assert len(collection.upserts) == 1
    assert gateway.calls

    # SQLite got the seven-table projection.
    store = ContentStore(content_db_path)
    try:
        assert store.count("highlight") == 1
        assert store.count("claim") == 1
    finally:
        store.close()


def test_run_document_captures_only_the_explicit_file(tmp_path: Path) -> None:
    requested = tmp_path / "requested.md"
    requested.write_text(
        "Duration measures interest rate sensitivity.",
        encoding="utf-8",
    )
    (tmp_path / "must-not-be-captured.md").write_text(
        "This file is outside the bounded run.",
        encoding="utf-8",
    )
    gateway = FakeGatewayClient()
    config = _config(tmp_path)
    kg = FakeKGStore()

    report = run_document(
        config,
        requested,
        kg_store=kg,
        vector_store=VectorStore(config.chroma_path, client=FakeChromaClient()),
        content_store=ContentStore(config.content_db_path),
        extractor=FixtureExtractor(),
        gateway_client=gateway,
    )

    assert report.captured_count == 1
    assert len(report.processed) == 1
    assert report.dispatched_counts == {"kg": 1, "vector": 1, "sqlite": 1}
    assert len([path for path in config.raw_root.rglob("*") if path.is_file()]) == 1


def test_one_shared_gateway_client_is_injected_into_every_model_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = FakeGatewayClient()
    vault = _make_vault(tmp_path, {"note.md": "Duration measures interest rate sensitivity."})
    _patch_capture(monkeypatch, vault)
    config = _config(tmp_path)
    chroma = FakeChromaClient()
    seen: dict[str, object] = {}
    real_vector_consumer = runner_module.VectorConsumer

    def build_extractor(*, chat_client):
        seen["extractor"] = chat_client
        return FixtureExtractor()

    def build_vector_store(path, *, embedding_client):
        seen["vector_store"] = embedding_client
        return VectorStore(path, client=chroma, embedding_client=embedding_client)

    def build_vector_consumer(store, *, embedding_client, chunk_config):
        seen["vector_consumer"] = embedding_client
        return real_vector_consumer(
            store,
            embedding_client=embedding_client,
            chunk_config=chunk_config,
        )

    def build_segmenter(*, chat_client, config):
        seen["segmenter"] = chat_client
        return HeadingTopicSegmenter()

    monkeypatch.setattr(runner_module, "GatewayExtractor", build_extractor)
    monkeypatch.setattr(runner_module, "GatewayTopicSegmenter", build_segmenter)
    monkeypatch.setattr(runner_module, "VectorStore", build_vector_store)
    monkeypatch.setattr(runner_module, "VectorConsumer", build_vector_consumer)

    content = ContentStore(config.content_db_path)
    try:
        report = run_ingestion(
            config,
            kg_store=FakeKGStore(),
            content_store=content,
            gateway_client=gateway,
        )
    finally:
        content.close()

    assert report.dispatched_counts == {"kg": 1, "vector": 1, "sqlite": 1}
    # The parse step is a model path too (T33), so it must share the one
    # gateway client rather than reaching for a provider of its own (R1).
    assert seen == {
        "extractor": gateway,
        "segmenter": gateway,
        "vector_store": gateway,
        "vector_consumer": gateway,
    }


def test_second_run_on_unchanged_vault_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = FakeGatewayClient()
    vault = _make_vault(tmp_path, {"note.md": "Duration measures interest rate sensitivity."})
    _patch_capture(monkeypatch, vault)
    config = _config(tmp_path)

    def _run() -> runner_module.RunReport:
        return run_ingestion(
            config,
            kg_store=FakeKGStore(),
            vector_store=VectorStore(config.chroma_path, client=FakeChromaClient()),
            content_store=ContentStore(config.content_db_path),
            extractor=FixtureExtractor(),
            gateway_client=gateway,
        )

    first = _run()
    second = _run()

    assert first.captured_count == 1
    assert len(first.processed) == 1
    # Same file, same hash -> capture is an exact duplicate, nothing new to process.
    assert second.captured_count == 1
    assert second.captured[0].exact_duplicate is True
    assert second.processed == []


def test_extraction_failure_on_one_item_does_not_abort_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = FakeGatewayClient()
    vault = _make_vault(
        tmp_path,
        {
            "good.md": "Duration measures interest rate sensitivity.",
            "bad.md": "FAIL_ME this note breaks extraction.",
        },
    )
    _patch_capture(monkeypatch, vault)
    config = _config(tmp_path)

    report = run_ingestion(
        config,
        kg_store=FakeKGStore(),
        vector_store=VectorStore(config.chroma_path, client=FakeChromaClient()),
        content_store=ContentStore(config.content_db_path),
        extractor=FixtureExtractor(fail_marker="FAIL_ME"),
        gateway_client=gateway,
    )

    assert report.captured_count == 2
    assert len(report.processed) == 2
    statuses = sorted(outcome.status for outcome in report.processed)
    assert statuses == ["extraction_failed", "processed"]
    assert report.failed_count == 1
    assert report.dispatched_counts == {"kg": 1, "vector": 1, "sqlite": 1}
