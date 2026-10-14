from datetime import datetime, timezone
from pathlib import Path
from .config import RAW_DATA_ROOT


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def bronze_dir(source: str) -> Path:
    return RAW_DATA_ROOT / "bronze" / today() / source / "bronze"


def triplets_dir(source: str, date: str) -> Path:
    return RAW_DATA_ROOT / "bronze" / date / source / "triplets"


def abs_path(rel: str) -> Path:
    return RAW_DATA_ROOT / rel
