from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from unified_ingestion.config import IngestionConfig, central_database_root
from unified_ingestion.dispatch import EnvelopeConsumer, JsonHandoffConsumer
from unified_ingestion.extraction import EmptySemanticExtractor, GatewaySemanticExtractor
from unified_ingestion.models import CaptureRequest
from unified_ingestion.pipeline import UnifiedIngestionPipeline
from unified_ingestion.sources import capture_markdown_tree


def _config(args: argparse.Namespace) -> IngestionConfig:
    return IngestionConfig(
        database_root=args.database_root,
        extraction_version=args.extraction_version,
        review_confidence_threshold=args.review_threshold,
    )


def _pipeline(args: argparse.Namespace) -> UnifiedIngestionPipeline:
    config = _config(args)
    extractor = (
        EmptySemanticExtractor()
        if args.offline
        else GatewaySemanticExtractor(
            base_url=args.gateway_url,
            model=args.model,
        )
    )
    consumers: list[EnvelopeConsumer] = [
        JsonHandoffConsumer("kg", config.handoff_root),
        JsonHandoffConsumer("vector", config.handoff_root),
    ]
    return UnifiedIngestionPipeline(config, extractor=extractor, consumers=consumers)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database-root", type=Path, default=central_database_root())
    parser.add_argument("--extraction-version", default="semantic_extraction_v1")
    parser.add_argument("--review-threshold", type=float, default=0.75)
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get("LLM_GATEWAY_URL", "http://127.0.0.1:8107"),
    )
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--offline", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified immutable ingestion pipeline")
    _add_common(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture", help="Capture one immutable raw record")
    capture.add_argument("--source-type", required=True)
    capture.add_argument("--origin", required=True)
    capture.add_argument("--file", type=Path, help="Read bytes from a file; stdin when omitted")
    capture.add_argument("--metadata", default="{}", help="JSON object")
    capture.add_argument("--legacy-source-id")

    capture_tree = subparsers.add_parser(
        "capture-tree", help="Capture every Markdown file under a read-only source tree"
    )
    capture_tree.add_argument("root", type=Path)
    capture_tree.add_argument("--source-type", default="note")
    capture_tree.add_argument("--metadata", default="{}", help="JSON object")

    process = subparsers.add_parser("process", help="Normalize, extract, review-gate, and dispatch")
    process.add_argument("--limit", type=int, default=100)

    review = subparsers.add_parser("review", help="Approve or reject a pending envelope")
    review.add_argument("envelope_id")
    review.add_argument("decision", choices=("approve", "reject"))
    review.add_argument("--resolver", required=True)
    review.add_argument("--note", default="")

    subparsers.add_parser("reviews", help="List pending semantic review items")
    subparsers.add_parser("retry-dispatches", help="Retry failed target handoffs idempotently")
    status = subparsers.add_parser("status", help="Return ledger counts")
    status.add_argument("--legacy-source-id")
    args = parser.parse_args(argv)

    try:
        with _pipeline(args) as pipeline:
            if args.command == "capture":
                content = args.file.read_bytes() if args.file else sys.stdin.buffer.read()
                metadata = json.loads(args.metadata)
                if not isinstance(metadata, dict):
                    raise ValueError("--metadata must be a JSON object")
                capture_result = pipeline.capture(
                    CaptureRequest(
                        source_type=args.source_type,
                        origin=args.origin,
                        content=content,
                        metadata=metadata,
                        legacy_source_id=args.legacy_source_id,
                    )
                )
                print(capture_result.model_dump_json(indent=2))
            elif args.command == "capture-tree":
                metadata = json.loads(args.metadata)
                if not isinstance(metadata, dict):
                    raise ValueError("--metadata must be a JSON object")
                results = capture_markdown_tree(
                    pipeline,
                    args.root,
                    source_type=args.source_type,
                    metadata=metadata,
                )
                print(
                    json.dumps(
                        [result.model_dump(mode="json") for result in results], indent=2
                    )
                )
            elif args.command == "process":
                print(
                    json.dumps(
                        [result.model_dump(mode="json") for result in pipeline.process_pending(args.limit)],
                        indent=2,
                    )
                )
            elif args.command == "review":
                review_result = pipeline.resolve_review(
                    args.envelope_id,
                    approved=args.decision == "approve",
                    resolver=args.resolver,
                    note=args.note,
                )
                print(review_result.model_dump_json(indent=2))
            elif args.command == "reviews":
                print(json.dumps(pipeline.store.pending_reviews(), indent=2))
            elif args.command == "retry-dispatches":
                print(
                    json.dumps(
                        [result.model_dump(mode="json") for result in pipeline.retry_dispatches()],
                        indent=2,
                    )
                )
            elif args.command == "status":
                counts: dict[str, Any] = {
                    table: len(list(pipeline.store.rows(table)))
                    for table in (
                        "source_records",
                        "captures",
                        "envelopes",
                        "review_queue",
                        "dispatches",
                        "quarantine",
                    )
                }
                if args.legacy_source_id:
                    counts["resolved_source_record_id"] = pipeline.store.resolve_legacy_reference(
                        args.legacy_source_id
                    )
                print(json.dumps(counts, indent=2))
        return 0
    except Exception as exc:
        print(f"unified ingestion failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
