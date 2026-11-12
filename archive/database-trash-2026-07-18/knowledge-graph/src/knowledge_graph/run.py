import logging
import os
import sys
from pathlib import Path

# TODO: manually triggered via Automator button; revisit scheduling (launchd nightly) once running on always-on hardware (Mac mini/Studio).
_raw_data_root = Path(os.environ["RAW_DATA_ROOT"])
sys.path.insert(0, str(_raw_data_root))

from lib.heartbeat import check_staleness, record_run_end, record_run_start
from lib.ledger import Item, init_ledger, is_done, pending

from knowledge_graph.extraction import extract_triplets
from knowledge_graph.ingestion import write_kg
from knowledge_graph.kg_store import KGStore

log = logging.getLogger(__name__)


def run_kg() -> None:
    init_ledger()
    rid = record_run_start("kg")
    store = KGStore()
    seen = done = failed = 0

    for item in pending("kg", "written"):
        seen += 1
        try:
            if is_done(item.content_hash, "kg", "extracted"):
                triplets_path = str(item.triplets_abs())
            else:
                triplets_path = extract_triplets(item)
            write_kg(item, triplets_path, store)
            done += 1
        except Exception as exc:
            failed += 1
            log.exception("item %s failed: %s", item.item_id, exc)

    record_run_end(rid, seen, done, failed, "ok" if not failed else "error")
    store.close()
    check_staleness()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_kg()
