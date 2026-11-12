import os
from pathlib import Path

_raw_data_root = os.environ.get("RAW_DATA_ROOT", "").strip()
if not _raw_data_root:
    raise RuntimeError("RAW_DATA_ROOT env var must be set to the 'Raw Data' folder path")

RAW_DATA_ROOT = Path(_raw_data_root).expanduser()
if not RAW_DATA_ROOT.exists():
    raise RuntimeError("RAW_DATA_ROOT env var must be set to the 'Raw Data' folder path")

SOURCE_REGISTRY = {
    "gm": "gmail",
    "pc": "podcast",
    "ar": "article",
    "nt": "note",
    "hl": "highlight",
}
ROUTING = {
    "gmail": {"vector", "sqlite"},
    "podcast": {"kg", "vector", "sqlite"},
    "article": {"kg", "vector", "sqlite"},
    "note": {"kg", "vector"},
    "highlight": {"kg", "vector", "sqlite"},
}

# The final stage that means "this target is fully done with an item" (P11:
# stage count varies per target). Used by the staleness check to decide whether
# an item routed to a target is still outstanding.
#
# Only list targets that have a working consumer. `sqlite` is in ROUTING but has
# no aligned consumer yet, so it's intentionally omitted — otherwise every
# gmail/article/podcast capture would nag as "stale for sqlite" forever. Add
# "sqlite": "written" here when that consumer lands.
TERMINAL_STAGE = {
    "kg": "written",
    "vector": "upserted",
}
