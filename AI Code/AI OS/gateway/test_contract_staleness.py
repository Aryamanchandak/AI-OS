from __future__ import annotations

import json
from pathlib import Path
import subprocess

from main import app


AI_OS_ROOT = Path(__file__).resolve().parents[1]
OPENAPI = Path(__file__).with_name("openapi.json")
SCHEMA = AI_OS_ROOT / "shell" / "src" / "api" / "schema.d.ts"
OPENAPI_TYPESCRIPT = (
    AI_OS_ROOT / "shell" / "node_modules" / ".bin" / "openapi-typescript"
)


def test_committed_openapi_schema_is_current(tmp_path: Path) -> None:
    generated = tmp_path / "openapi.json"
    generated.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    assert OPENAPI.read_bytes() == generated.read_bytes(), (
        "gateway/openapi.json is stale; run `python export_openapi.py`"
    )


def test_committed_typescript_schema_is_current(tmp_path: Path) -> None:
    generated = tmp_path / "schema.d.ts"
    subprocess.run(
        [str(OPENAPI_TYPESCRIPT), str(OPENAPI), "-o", str(generated)],
        check=True,
        cwd=AI_OS_ROOT / "shell",
    )
    assert SCHEMA.read_bytes() == generated.read_bytes(), (
        "shell/src/api/schema.d.ts is stale; run `npm run types:generate`"
    )
