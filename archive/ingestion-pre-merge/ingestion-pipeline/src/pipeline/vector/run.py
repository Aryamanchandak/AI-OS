"""Vector consumer orchestrator — the single entry point the button calls.

Mirrors knowledge_graph.run: drive off the ledger's pending() query, process
each routed item, record the run, then fire the staleness heartbeat.

    RAW_DATA_ROOT=".../Database/Raw Data" \\
    CHROMA_PATH=".../Database/vector-db/chroma_store" \\   # optional
    .venv/bin/python -m vector_db.run
"""

import logging
import os
from pathlib import Path

from pipeline.core.config import RAW_DATA_ROOT
from pipeline.core.heartbeat import check_staleness, record_run_end, record_run_start
from pipeline.core.ledger import init_ledger, pending

from pipeline.vector.vector_store import VectorStore
from pipeline.vector.write import COLLECTION, write_vector

log = logging.getLogger(__name__)


def _default_chroma_path() -> Path:
    env = os.environ.get("CHROMA_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    # Derived, disposable store (rebuildable from bronze) — lives with the data.
    return RAW_DATA_ROOT.parent / "chroma"


def run_vector() -> None:
    init_ledger()
    rid = record_run_start("vector")
    store = VectorStore(chroma_path=_default_chroma_path())
    seen = done = failed = 0

    items = pending("vector", "upserted")

    # Fail the whole run fast if the embedder can't write (e.g. Ollama installed
    # but down) — otherwise every item fails one-by-one. This is a live probe, so
    # it catches what the per-item ensure_embedder() guard alone cannot. Gated on
    # there being work: a no-op re-run (nothing pending) must stay a no-op and not
    # error just because Ollama happens to be down.
    if items:
        try:
            store.assert_writable(COLLECTION)
        except Exception as exc:
            log.error("run_vector aborting — embedder not writable: %s", exc)
            record_run_end(rid, seen, done, failed, "error")
            check_staleness()
            return

    for item in items:
        seen += 1
        try:
            write_vector(item, store)
            done += 1
        except Exception as exc:  # write_vector already marked (vector, upserted, failed)
            failed += 1
            log.exception("item %s failed: %s", item.item_id, exc)

    record_run_end(rid, seen, done, failed, "ok" if not failed else "error")
    log.info("run_vector done — seen=%d done=%d failed=%d", seen, done, failed)
    check_staleness()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_vector()
