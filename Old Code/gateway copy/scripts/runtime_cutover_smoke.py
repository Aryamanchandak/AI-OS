"""Run a real Gateway listener through cold start, restart, and crash recovery.

Uses an isolated source snapshot and temporary database, without either old
submodule. Run from gateway with ``.venv/bin/python scripts/runtime_cutover_smoke.py``.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

import httpx


SOURCE = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _ready(port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Gateway exited during startup with code {process.returncode}")
        try:
            with httpx.Client(timeout=0.3) as client:
                response = client.get(f"http://127.0.0.1:{port}/health")
                if response.status_code == 200 and response.json() == {"status": "ok"}:
                    diagnostic = client.get(
                        f"http://127.0.0.1:{port}/api/diagnostics/services",
                        headers={"Authorization": "Bearer standalone-test-token"},
                    )
                    assert diagnostic.status_code == 200, diagnostic.text
                    assert diagnostic.json()["services"]["gateway"]["address"].endswith(f":{port}")
                    return
        except httpx.ConnectError:
            pass
        time.sleep(0.05)
    raise TimeoutError("Gateway did not become ready")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="gateway-cutover-") as directory:
        root = Path(directory)
        snapshot = root / "gateway"
        snapshot.mkdir()
        shutil.copytree(SOURCE / "src", snapshot / "src", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(SOURCE / "config", snapshot / "config")
        shutil.copy2(SOURCE / "main.py", snapshot / "main.py")
        port = _free_port()
        environment = os.environ.copy()
        environment.update({
            "PYTHONPATH": str(snapshot / "src"),
            "AI_OS_PREVIEW": "1",
            "AI_OS_TOKEN": "standalone-test-token",
            "AI_OS_SERVICE_GATEWAY_PORT": str(port),
        })
        environment.pop("AI_OS_SERVICE_REGISTRY_PATH", None)
        for name in ("GLC_GATEWAY_DB", "GLC_AUDIT_DB", "GLC_PAIRING_DB", "GLC_CACHE_DB"):
            environment.pop(name, None)
        log_path = root / "gateway.log"
        backup = root / "backup"
        with log_path.open("wb") as log:
            for phase in ("cold start", "restart", "crash recovery"):
                process = subprocess.Popen(
                    [sys.executable, "main.py"], cwd=snapshot, env=environment,
                    stdout=log, stderr=subprocess.STDOUT,
                )
                try:
                    _ready(port, process)
                    print(f"{phase}: ready on {port}")
                except BaseException:
                    print(log_path.read_text(encoding="utf-8", errors="replace")[-3000:])
                    raise
                finally:
                    if phase == "restart":
                        process.kill()
                    else:
                        process.terminate()
                    process.wait(timeout=5)
                if phase == "cold start":
                    backup.mkdir()
                    databases = sorted((root / "Database").rglob("*.sqlite"))
                    assert databases, "Gateway created no SQLite files to back up"
                    for database in databases:
                        target = backup / database.relative_to(root / "Database")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with sqlite3.connect(database) as source, sqlite3.connect(target) as destination:
                            source.backup(destination)
                    print(f"backup: {len(databases)} SQLite files")
                if phase == "restart":
                    for saved in backup.rglob("*.sqlite"):
                        destination = root / "Database" / saved.relative_to(backup)
                        for suffix in ("-wal", "-shm"):
                            destination.with_name(destination.name + suffix).unlink(missing_ok=True)
                        shutil.copy2(saved, destination)
                    print("restore: SQLite backup copied before crash-recovery start")


if __name__ == "__main__":
    main()
