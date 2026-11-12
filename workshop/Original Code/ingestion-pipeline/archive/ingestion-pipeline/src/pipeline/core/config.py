import os
from pathlib import Path

# Data root resolution: RAW_DATA_ROOT env var wins; otherwise default to the
# sibling data store at "<AI Code>/Database/Raw Data" (this repo lives at
# "<AI Code>/ingestion-pipeline"). Code and data are deliberately separate trees.
_DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "Database" / "Raw Data"
_raw_data_root = os.environ.get("RAW_DATA_ROOT", "").strip()

RAW_DATA_ROOT = Path(_raw_data_root).expanduser() if _raw_data_root else _DEFAULT_ROOT
if not RAW_DATA_ROOT.exists():
    raise RuntimeError(
        f"Data root not found at {RAW_DATA_ROOT}. Set RAW_DATA_ROOT to the 'Raw Data' folder path."
    )

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
