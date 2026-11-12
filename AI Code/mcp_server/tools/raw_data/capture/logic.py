from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _raw_data_root() -> Path:
    raw_data_root = os.environ.get("RAW_DATA_ROOT", "").strip()
    if not raw_data_root:
        raise RuntimeError("RAW_DATA_ROOT env var must be set to the 'Raw Data' folder path")
    path = Path(raw_data_root).expanduser()
    if not path.exists():
        raise RuntimeError("RAW_DATA_ROOT env var must be set to the 'Raw Data' folder path")
    return path


def _add_raw_data_lib_to_path() -> Path:
    raw_data_root = _raw_data_root()
    raw_data_root_str = str(raw_data_root)
    if raw_data_root_str not in sys.path:
        sys.path.insert(0, raw_data_root_str)
    return raw_data_root


def capture_raw_data(
    source: str,
    content: str,
    authored: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write immutable bronze content through Raw Data's sanctioned capture() path."""
    _add_raw_data_lib_to_path()
    from lib.capture import capture

    result = capture(source=source, content=content, authored=authored, metadata=metadata)
    return result.model_dump()


def raw_data_status(target: str = "kg", max_age_days: int = 3) -> dict[str, Any]:
    """Return ledger-based pending and staleness status without reading bronze content."""
    _add_raw_data_lib_to_path()
    from lib.heartbeat import staleness_report
    from lib.ledger import pending

    return {
        "target": target,
        "max_age_days": max_age_days,
        "pending_count": len(pending(target, "written")),
        "staleness": staleness_report(max_age_days=max_age_days),
    }
