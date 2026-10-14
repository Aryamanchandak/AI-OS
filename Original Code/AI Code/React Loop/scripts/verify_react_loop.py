#!/usr/bin/env python3
"""Reproducible functional verification for React Loop runtime plumbing."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def _wait_for_server(base_url: str, timeout_s: float = 15) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        try:
            status, _ = _get(f"{base_url}/")
            if status == 200:
                return
            last_error = f"status={status}"
        except Exception as exc:  # noqa: BLE001 - startup polling
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"server did not become ready: {last_error}")


def _start_server(port: int, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "react_loop.web:app", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stop_server(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


async def _mcp_file_check(store: Path) -> Check:
    from react_loop.config import ServerConfig
    from react_loop.mcp_client import MCPClient

    default_path = ROOT / "podcast_tools" / "data" / "verify_harness_mcp.txt"
    if default_path.exists():
        default_path.unlink()
    server = ServerConfig(
        command=sys.executable,
        args=["-m", "simple_server"],
        cwd=str(ROOT),
    )
    async with MCPClient(server) as client:
        created = await client.call_tool(
            "file_create",
            {"name": "verify_harness_mcp.txt", "content": "MCP_ENV_OK"},
        )
        read = await client.call_tool(
            "file_read",
            {"name": "verify_harness_mcp.txt"},
        )
    expected = store / "verify_harness_mcp.txt"
    ok = (
        "CREATED" in created
        and read == "MCP_ENV_OK"
        and expected.exists()
        and not default_path.exists()
    )
    return Check("MCP tools honour CRUD_FILES_DIR", ok, created)


def run(args: argparse.Namespace) -> int:
    checks: list[Check] = []
    temp_root = Path(tempfile.mkdtemp(prefix="react-loop-verify-"))
    store = temp_root / "store"
    env = os.environ.copy()
    env["CRUD_FILES_DIR"] = str(store)
    env["APP_BASE_URL"] = args.base_url or f"http://127.0.0.1:{args.port}"
    env.setdefault("PYTHONPATH", str(ROOT))

    server: subprocess.Popen[str] | None = None
    failed = False
    try:
        os.environ.update({"CRUD_FILES_DIR": str(store), "APP_BASE_URL": env["APP_BASE_URL"]})

        from simple_server.tools.files import file_create, file_read, file_update, file_write_json
        from simple_server.tools.generative_ui import render_ui, render_ui_from_json

        invalid = file_create("bad.json", "[item for item in range(3)]")
        checks.append(Check(
            "Invalid JSON is rejected",
            invalid.startswith("ERROR: Invalid JSON") and not (store / "bad.json").exists(),
            invalid,
        ))

        file_create("safe.json", '{"ok": true}')
        rejected = file_update("safe.json", "{'ok': False}")
        checks.append(Check(
            "Invalid JSON update preserves existing file",
            rejected.startswith("ERROR: Invalid JSON") and json.loads(file_read("safe.json")) == {"ok": True},
            rejected,
        ))

        structured = file_write_json("rows.json", [{"name": "Harness Row", "value": 1}])
        checks.append(Check(
            "Structured JSON writer creates parseable JSON",
            "valid JSON" in structured and json.loads(file_read("rows.json"))[0]["name"] == "Harness Row",
            structured,
        ))

        server = _start_server(args.port, env)
        _wait_for_server(env["APP_BASE_URL"])

        ui_code = """
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Text

with PrefabApp() as app:
    with Column():
        Text(data[0]["name"])
"""
        rendered = render_ui_from_json("rows.json", ui_code)
        ui_status, ui_body = _get(f"{env['APP_BASE_URL']}/ui/latest")
        checks.append(Check(
            "UI renders from persisted JSON data",
            "UI rendered successfully" in rendered and ui_status == 200 and "Harness Row" in ui_body,
            f"render={rendered.splitlines()[0] if rendered else ''}; status={ui_status}",
        ))

        _stop_server(server)
        server = _start_server(args.port, env)
        _wait_for_server(env["APP_BASE_URL"])
        persisted_status, persisted_body = _get(f"{env['APP_BASE_URL']}/ui/latest")
        checks.append(Check(
            "/ui/latest persists after restart",
            persisted_status == 200 and "Harness Row" in persisted_body,
            f"status={persisted_status}",
        ))

        snapshot = store / "generated_ui" / "index.html"
        snapshot.unlink()
        missing_status, _ = _get(f"{env['APP_BASE_URL']}/ui/latest")
        checks.append(Check(
            "Missing snapshot returns 404",
            missing_status == 404,
            f"status={missing_status}",
        ))

        general_render = render_ui("""
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Text

with PrefabApp() as app:
    with Column():
        Text("Configured URL")
""")
        checks.append(Check(
            "Generated UI URL uses APP_BASE_URL",
            f"{env['APP_BASE_URL']}/ui/latest" in general_render,
            general_render.replace("\n", " | "),
        ))

        checks.append(asyncio.run(_mcp_file_check(store)))
    except Exception as exc:  # noqa: BLE001 - report all verification failures
        failed = True
        checks.append(Check("verification harness exception", False, repr(exc)))
    finally:
        if server is not None:
            _stop_server(server)

    failed = failed or any(not check.passed for check in checks)
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        detail = f" - {check.detail}" if check.detail else ""
        print(f"{status}: {check.name}{detail}")

    if failed and args.keep_on_failure:
        print(f"Artifacts preserved: {temp_root}")
    else:
        shutil.rmtree(temp_root, ignore_errors=True)

    if not args.browser:
        print("Functional UI verification passed." if not failed else "Functional UI verification failed.")
        print("Visual screenshot verification skipped because no browser backend was requested.")

    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--keep-on-failure", action="store_true")
    parser.add_argument("--browser", action="store_true", help="reserved for optional visual checks")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
