"""Gateway starts from a source snapshot with no legacy sibling repositories."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_gateway_boots_without_glc_or_ingestion_submodules(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    snapshot = tmp_path / "gateway"
    snapshot.mkdir()
    shutil.copytree(source / "src", snapshot / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(source / "config", snapshot / "config")
    shutil.copy2(source / "main.py", snapshot / "main.py")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(snapshot / "src")
    environment["AI_OS_PREVIEW"] = "1"
    environment["AI_OS_TOKEN"] = "standalone-test-token"
    environment.pop("AI_OS_SERVICE_REGISTRY_PATH", None)
    for name in ("GLC_GATEWAY_DB", "GLC_AUDIT_DB", "GLC_PAIRING_DB", "GLC_CACHE_DB"):
        environment.pop(name, None)

    check = """
from fastapi.testclient import TestClient
from main import create_app
with TestClient(create_app(token='standalone-test-token')) as client:
    assert client.get('/health').json() == {'status': 'ok'}
    response = client.get('/api/diagnostics/services', headers={'Authorization': 'Bearer standalone-test-token'})
    assert response.status_code == 200, response.text
"""
    result = subprocess.run(
        [sys.executable, "-c", check],
        cwd=snapshot,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
