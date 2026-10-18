from __future__ import annotations

import json
from pathlib import Path

from main import app


OPENAPI = Path(__file__).resolve().parents[1] / "contracts" / "openapi.json"


def test_committed_openapi_schema_is_current(tmp_path: Path) -> None:
    generated = tmp_path / "openapi.json"
    generated.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    assert OPENAPI.read_bytes() == generated.read_bytes(), (
        "gateway/contracts/openapi.json is stale; run `python scripts/export_openapi.py`"
    )
