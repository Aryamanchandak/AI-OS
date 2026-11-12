from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class RunReportView:
    run_id: str
    path: Path
    data: Mapping[str, Any]


def write_report(reports_root: Path, run_id: str, data: Mapping[str, Any]) -> RunReportView:
    reports_root.mkdir(parents=True, exist_ok=True)
    path = reports_root / f"{run_id}.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return RunReportView(run_id=run_id, path=path, data=dict(data))


def read_report(reports_root: Path, run_id: str | None = None) -> RunReportView:
    if run_id is None:
        candidates = sorted(
            reports_root.glob("*.json"), key=lambda path: path.stat().st_mtime
        )
        if not candidates:
            raise FileNotFoundError("no completed coordinator reports exist")
        path = candidates[-1]
        run_id = path.stem
    else:
        path = reports_root / f"{run_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid run report: {path}")
    return RunReportView(run_id=run_id, path=path, data=data)
