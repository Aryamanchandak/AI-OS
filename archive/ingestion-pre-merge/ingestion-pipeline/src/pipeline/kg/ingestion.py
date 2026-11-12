"""Write extracted triplets from Raw Data into Neo4j."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pipeline.kg.identity import normalize_label

if TYPE_CHECKING:
    from pipeline.core.ledger import Item
    from pipeline.kg.kg_store import KGStore

logger = logging.getLogger(__name__)


def write_kg(item: "Item", triplets_path: str, store: "KGStore") -> None:
    """
    Read triplets JSONL from Raw Data, MERGE into Neo4j via store.execute_write.
    Idempotent (MERGE on subject_id + relation + object_id).
    Marks ledger stage (kg, written).
    """
    from pipeline.core.ledger import mark
    from pipeline.kg.kg_store import _UPSERT_EDGE_ROWS_CYPHER

    rows = []
    with open(triplets_path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            data = json.loads(line)
            rows.append({
                "subject_id": data["subject"],
                "subject_name": data["subject_name"],
                "subject_normalized_name": normalize_label(data["subject_name"]),
                "subject_domain": data.get("domain", "general"),
                "relation": data["predicate"],
                "object_id": data["object"],
                "object_name": data["object_name"],
                "object_normalized_name": normalize_label(data["object_name"]),
                "object_domain": data.get("domain", "general"),
                "id": str(uuid.uuid4()),
                "source": item.item_id,
                "source_hash": data["source_hash"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    if not rows:
        logger.warning("[write_kg] %s: triplets file empty - nothing to write", item.item_id)
        mark(item.content_hash, "kg", "written", "done")
        return

    try:
        ok, error = store.execute_write(_UPSERT_EDGE_ROWS_CYPHER, rows=rows)
        if not ok:
            raise RuntimeError(error)
        mark(item.content_hash, "kg", "written", "done")
        logger.info("[write_kg] %s: %d edges written to Neo4j", item.item_id, len(rows))
    except Exception as exc:
        mark(item.content_hash, "kg", "written", "failed", error=str(exc))
        raise
