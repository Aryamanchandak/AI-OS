#!/usr/bin/env python3
"""Run T5 against one document and verify every live projection.

Since T33 a document is parsed into N highlights and each one gets its own
envelope, so this verifies every highlight of the fixture, not just the first.
It also counts real gateway chat calls and checks them against
``ceil(highlights / extraction_batch_size) + segmentation calls`` — the batching
claim is a cost claim, so it is measured rather than asserted.

The operational data is isolated under a temporary Database root. Neo4j is the
only shared store touched; this script removes the fixture's exact
highlight-scoped graph contributions in ``finally`` unless ``--keep-graph`` is
explicitly supplied.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import gateway.ingestion.runner as runner_module
from gateway.ingestion.config import IngestionConfig, central_database_root, load_root_env
from gateway.ingestion.ids import highlight_id_for_highlight
from gateway.ingestion.kg.kg_store import KGStore
from gateway.ingestion.models import IngestionEnvelope
from gateway.ingestion.runner import RunReport, run_document
from gateway.ingestion.vector.vector_store import VectorStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = PROJECT_ROOT / "ingestion_tests" / "fixtures" / "t5_live_smoke.md"
EXPECTED_TARGETS = {"kg", "sqlite", "vector"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run and verify the bounded, live T5 ingestion smoke test."
    )
    parser.add_argument(
        "document",
        nargs="?",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="one Markdown document to ingest (default: controlled T5 fixture)",
    )
    parser.add_argument(
        "--database-root",
        type=Path,
        help="retain SQLite/Chroma/bronze artifacts here instead of a temp directory",
    )
    parser.add_argument(
        "--neo4j-data-root",
        type=Path,
        help=(
            "expected physical data directory of the shared Neo4j server "
            "(default: the central Database/neo4j directory)"
        ),
    )
    parser.add_argument(
        "--keep-graph",
        action="store_true",
        help="leave this fixture's exact provenance-scoped contribution in Neo4j",
    )
    return parser


class CountingGatewayClient:
    """Pass-through proxy that counts real gateway calls.

    Wraps the one shared client rather than creating a second one: this exists
    to measure the batching payoff, not to add another model path.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.chat_calls = 0
        self.embed_calls = 0

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        self.chat_calls += 1
        return self._inner.chat(*args, **kwargs)

    def embed(self, *args: Any, **kwargs: Any) -> Any:
        self.embed_calls += 1
        return self._inner.embed(*args, **kwargs)

    def resolve_chat_profile(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.resolve_chat_profile(*args, **kwargs)


def _envelopes(config: IngestionConfig, report: RunReport) -> list[IngestionEnvelope]:
    envelopes: list[IngestionEnvelope] = []
    for outcome in report.processed:
        if outcome.envelope_id is None:
            raise RuntimeError(
                f"highlight {outcome.highlight_index} produced no envelope: "
                f"{outcome.status}"
            )
        path = config.envelope_root / f"{outcome.envelope_id}.json"
        envelopes.append(
            IngestionEnvelope.model_validate_json(path.read_text(encoding="utf-8"))
        )
    return envelopes


def _dispatch_rows(config: IngestionConfig, envelope_id: str) -> list[dict[str, Any]]:
    with sqlite3.connect(config.ledger_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT target,status,attempts,artifact_ref,error
               FROM dispatches WHERE envelope_id=? ORDER BY target""",
            (envelope_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _content_counts(
    config: IngestionConfig, *, source_record_id: str, highlight_ids: list[str]
) -> dict[str, int]:
    placeholders = ",".join("?" for _ in highlight_ids)
    with sqlite3.connect(config.content_db_path) as connection:
        source_count = connection.execute(
            """SELECT COUNT(*) FROM acquisition
               WHERE origin_record_id=? AND file_hash IS NOT NULL""",
            (source_record_id,),
        ).fetchone()[0]
        highlight_count = connection.execute(
            f"""SELECT COUNT(*) FROM highlight
                WHERE highlight_id IN ({placeholders})
                  AND content_hash IS NOT NULL AND text IS NOT NULL""",
            highlight_ids,
        ).fetchone()[0]
        claim_count = connection.execute(
            f"SELECT COUNT(*) FROM claim WHERE highlight_id IN ({placeholders})",
            highlight_ids,
        ).fetchone()[0]
        transformation_count = connection.execute(
            f"SELECT COUNT(*) FROM transformation WHERE derived_from IN ({placeholders})",
            highlight_ids,
        ).fetchone()[0]
    return {
        "acquisitions": int(source_count),
        "highlights": int(highlight_count),
        "claims": int(claim_count),
        "transformations": int(transformation_count),
    }


def _graph_counts(highlight_ids: list[str]) -> dict[str, int]:
    from neo4j import GraphDatabase

    uri = os.environ["NEO4J_URI"]
    username = os.environ["NEO4J_USERNAME"]
    password = os.environ["NEO4J_PASSWORD"]
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    queries = {
        "concepts": (
            "MATCH (n:Concept) "
            "WHERE any(h IN $highlight_ids "
            "          WHERE h IN coalesce(n.contributing_highlight_ids, [])) "
            "RETURN count(n) AS count"
        ),
        "claims": (
            "MATCH (n:Claim) WHERE n.highlight_id IN $highlight_ids "
            "RETURN count(n) AS count"
        ),
        "relations": (
            "MATCH ()-[r:KG_EDGE]->() "
            "WHERE any(h IN $highlight_ids WHERE h IN coalesce(r.highlight_ids, [])) "
            "RETURN count(r) AS count"
        ),
    }
    counts: dict[str, int] = {}
    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        for label, query in queries.items():
            records, _, _ = driver.execute_query(
                query,
                highlight_ids=highlight_ids,
                database_=database,
            )
            counts[label] = int(records[0]["count"])
    return counts


def _vector_rows(
    config: IngestionConfig,
    *,
    source_record_id: str,
    envelopes: list[IngestionEnvelope],
) -> list[dict[str, Any]]:
    by_envelope_id = {envelope.envelope_id: envelope for envelope in envelopes}
    hits = VectorStore(config.chroma_path).get(
        "knowledge", where={"source_id": source_record_id}
    )
    rows: list[dict[str, Any]] = []
    for hit in hits:
        metadata = hit.metadata
        envelope = by_envelope_id.get(str(metadata.get("envelope_id")))
        if envelope is None:
            raise AssertionError(
                f"Chroma row {hit.id!r} names an envelope this run never wrote: "
                f"{metadata.get('envelope_id')!r}"
            )
        expected = {
            "source_id": source_record_id,
            "envelope_id": envelope.envelope_id,
            "highlight_id": highlight_id_for_highlight(
                source_record_id, envelope.highlight_index
            ),
            "highlight_index": envelope.highlight_index,
            "raw_content_hash": envelope.raw_content_hash,
            "normalized_content_hash": envelope.normalized_content_hash,
            "version": envelope.version,
        }
        mismatches = {
            key: {"expected": value, "actual": metadata.get(key)}
            for key, value in expected.items()
            if metadata.get(key) != value
        }
        if mismatches:
            raise AssertionError(f"Chroma provenance mismatch: {mismatches}")
        rows.append(
            {
                "id": hit.id,
                "characters": len(hit.text),
                "highlight_index": envelope.highlight_index,
                "chunk_index": metadata.get("chunk_index"),
                "chunk_total": metadata.get("chunk_total"),
            }
        )
    # Sibling highlights must not collide on a Chroma id — that would silently
    # overwrite one highlight's vector with another's.
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise AssertionError(f"Chroma ids collided across highlights: {sorted(ids)}")
    return rows


def _assert_first_run(report: RunReport, envelopes: list[IngestionEnvelope]) -> None:
    if report.captured_count != 1:
        raise AssertionError(
            f"bounded run expected 1 capture, got {report.captured_count}"
        )
    if not report.processed:
        raise AssertionError("document produced no highlights to process")
    by_index = {envelope.highlight_index: envelope for envelope in envelopes}
    for outcome in report.processed:
        if outcome.status != "processed":
            envelope = by_index.get(outcome.highlight_index or -1)
            detail: dict[str, Any] = {
                "highlight_index": outcome.highlight_index,
                "status": outcome.status,
            }
            if envelope is not None:
                detail.update(
                    {
                        "highlight_text": envelope.highlight_text,
                        "model_confidence": envelope.model_confidence,
                        "semantic_counts": {
                            "concepts": len(envelope.semantic.concepts),
                            "claims": len(envelope.semantic.claims),
                            "relations": len(envelope.semantic.relations),
                        },
                        "review_signals": [
                            signal.model_dump(mode="json")
                            for signal in envelope.review_signals
                        ],
                    }
                )
            raise AssertionError(
                "a highlight did not clear extraction/review:\n"
                + json.dumps(detail, indent=2, sort_keys=True)
            )
        if set(outcome.dispatched_targets) != EXPECTED_TARGETS:
            raise AssertionError(
                f"highlight {outcome.highlight_index}: expected dispatches "
                f"{sorted(EXPECTED_TARGETS)}, got {sorted(outcome.dispatched_targets)}"
            )


def _run(
    config: IngestionConfig,
    document: Path,
    *,
    keep_graph: bool,
    neo4j_data_root: Path,
) -> dict[str, Any]:
    highlight_ids: list[str] = []
    gateway = CountingGatewayClient(runner_module._shared_gateway_client())
    kg = KGStore(strict=True, expected_data_root=neo4j_data_root)
    try:
        first = run_document(
            config,
            document,
            metadata={"title": "T5 controlled live smoke fixture"},
            kg_store=kg,
            gateway_client=gateway,
        )
        envelopes = _envelopes(config, first)
        _assert_first_run(first, envelopes)
        source_record_id = first.captured[0].source_record_id
        highlight_ids = [
            highlight_id_for_highlight(source_record_id, envelope.highlight_index)
            for envelope in envelopes
        ]

        # The batching claim is a cost claim, so measure it. Extraction costs
        # ceil(highlights / batch_size) chat calls; segmentation adds at most
        # one call per highlight block on top (blocks under the semantic floor
        # are never sent at all).
        expected_extraction_calls = math.ceil(
            len(envelopes) / config.extraction_batch_size
        )
        if gateway.chat_calls < expected_extraction_calls:
            raise AssertionError(
                f"fewer chat calls ({gateway.chat_calls}) than the "
                f"{expected_extraction_calls} extraction calls this run required"
            )
        if gateway.chat_calls > expected_extraction_calls + len(envelopes):
            raise AssertionError(
                f"chat calls ({gateway.chat_calls}) exceed the batching budget: "
                f"{expected_extraction_calls} extraction + at most "
                f"{len(envelopes)} segmentation"
            )

        dispatches: list[dict[str, Any]] = []
        for envelope in envelopes:
            rows = _dispatch_rows(config, envelope.envelope_id)
            if {(row["target"], row["status"]) for row in rows} != {
                (target, "done") for target in EXPECTED_TARGETS
            }:
                raise AssertionError(
                    f"dispatch ledger is incomplete for highlight "
                    f"{envelope.highlight_index}: {rows}"
                )
            dispatches.extend(
                {**row, "highlight_index": envelope.highlight_index} for row in rows
            )

        graph = _graph_counts(highlight_ids)
        if any(graph[key] < 1 for key in ("concepts", "claims", "relations")):
            raise AssertionError(f"Neo4j projection is incomplete: {graph}")

        vectors = _vector_rows(
            config, source_record_id=source_record_id, envelopes=envelopes
        )
        if len(vectors) < len(envelopes):
            raise AssertionError(
                f"Chroma holds {len(vectors)} chunk(s) for {len(envelopes)} highlight(s)"
            )

        content = _content_counts(
            config, source_record_id=source_record_id, highlight_ids=highlight_ids
        )
        if content["highlights"] != len(highlight_ids):
            raise AssertionError(
                f"SQLite holds {content['highlights']} highlight row(s) for "
                f"{len(highlight_ids)} highlight(s)"
            )
        if any(content[key] < 1 for key in ("acquisitions", "claims")):
            raise AssertionError(f"SQLite projection is incomplete: {content}")

        second = run_document(
            config,
            document,
            metadata={"title": "T5 controlled live smoke fixture"},
            kg_store=kg,
            gateway_client=gateway,
        )
        if not second.captured[0].exact_duplicate:
            raise AssertionError("second capture was not recognized as an exact duplicate")
        if second.processed:
            raise AssertionError(
                f"duplicate unexpectedly re-entered processing: {second.processed}"
            )
        graph_after = _graph_counts(highlight_ids)
        vectors_after = _vector_rows(
            config, source_record_id=source_record_id, envelopes=envelopes
        )
        content_after = _content_counts(
            config, source_record_id=source_record_id, highlight_ids=highlight_ids
        )
        if graph_after != graph or len(vectors_after) != len(vectors) or content_after != content:
            raise AssertionError("duplicate run changed one or more projections")

        return {
            "result": "PASS",
            "document": str(document.resolve()),
            "artifact_database_root": str(config.database_root),
            "neo4j_data_root": str(neo4j_data_root),
            "source_record_id": source_record_id,
            "highlights": [
                {
                    "highlight_index": envelope.highlight_index,
                    "highlight_id": highlight_id,
                    "envelope_id": envelope.envelope_id,
                    "characters": len(envelope.highlight_text),
                    "has_context": envelope.highlight_context_text is not None,
                    "location": (
                        f"{envelope.highlight_start_char}:{envelope.highlight_end_char}"
                    ),
                    "model_confidence": envelope.model_confidence,
                    "semantic": {
                        "concepts": len(envelope.semantic.concepts),
                        "claims": len(envelope.semantic.claims),
                        "relations": len(envelope.semantic.relations),
                        "evidence_refs": sum(
                            len(proposal.evidence)
                            for proposal in (
                                *envelope.semantic.concepts,
                                *envelope.semantic.claims,
                                *envelope.semantic.relations,
                            )
                        ),
                    },
                    "review_signals": [
                        signal.model_dump(mode="json")
                        for signal in envelope.review_signals
                    ],
                }
                for envelope, highlight_id in zip(envelopes, highlight_ids)
            ],
            "gateway_calls": {
                "chat": gateway.chat_calls,
                "embed": gateway.embed_calls,
                "extraction_calls_expected": expected_extraction_calls,
                "naive_per_highlight_calls": len(envelopes),
            },
            "dispatches": dispatches,
            "neo4j": graph,
            "chroma": {"chunks": len(vectors), "rows": vectors},
            "sqlite": content,
            "idempotency": {
                "exact_duplicate": True,
                "projection_counts_unchanged": True,
            },
            "graph_cleanup": "retained" if keep_graph else "provenance-scoped",
        }
    finally:
        try:
            if highlight_ids and not keep_graph:
                for highlight_id in highlight_ids:
                    kg.purge_contributions(highlight_id)
        finally:
            kg.close()


def main() -> None:
    args = _parser().parse_args()
    document = args.document.expanduser().resolve()
    if not document.is_file():
        raise SystemExit(f"Document not found: {document}")
    load_root_env(PROJECT_ROOT)
    neo4j_data_root = (
        args.neo4j_data_root.expanduser().resolve()
        if args.neo4j_data_root is not None
        else (central_database_root(PROJECT_ROOT) / "neo4j").resolve()
    )

    if args.database_root is not None:
        root = args.database_root.expanduser().resolve()
        report = _run(
            IngestionConfig(database_root=root),
            document,
            keep_graph=args.keep_graph,
            neo4j_data_root=neo4j_data_root,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="ingestion-t5-") as temporary:
            report = _run(
                IngestionConfig(database_root=Path(temporary) / "Database"),
                document,
                keep_graph=args.keep_graph,
                neo4j_data_root=neo4j_data_root,
            )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
