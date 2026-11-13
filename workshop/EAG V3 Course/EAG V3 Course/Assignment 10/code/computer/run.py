"""Run or plan the assignment tasks; imports and --dry-run never touch the desktop."""
from __future__ import annotations
import asyncio
import json
import socket
import sys
import tempfile
import time
from pathlib import Path

from schemas import NodeSpec
from .backend import CuaDriver, CuaError, driver_scope, get_driver
from .skill import ComputerSkill
from .tasks import TASKS, canvas_url

ROOT = Path(__file__).resolve().parent.parent
TRAJ_ROOT = ROOT.parent / "evidence" / "trajectories"


def preflight():
    driver = CuaDriver()
    try:
        driver.require_daemon()
        checks = driver.call("check_permissions", {"prompt": False})
        return {"driver": True, **checks}
    except (CuaError, PermissionError) as exc:
        return {"driver": False, "error": str(exc)}


def print_preflight(checks):
    print("Preflight (no permission dialogs)")
    for key in ("driver", "accessibility", "screen_recording"):
        print(f"  {key}: {'OK' if checks.get(key) is True else 'MISSING'}")
    if checks.get("error"):
        print(f"  {checks['error']}")
    return (all(checks.get(k) is True for k in ("driver", "accessibility", "screen_recording"))
            and checks.get("screen_recording_capturable", True) is True)


def _remember_launch(meta, launched):
    if not isinstance(launched, dict) or not launched.get("pid"):
        raise CuaError("launch_app returned no process ID")
    meta["pid"] = int(launched["pid"])
    windows = launched.get("windows", [])
    if windows:
        meta["window_id"] = int(windows[0]["window_id"])


def setup_calculator(meta):
    _remember_launch(meta, get_driver().call("launch_app", {"bundle_id": "com.apple.calculator"}))
    return True, "Calculator launched; clear is part of the recorded key sequence"


def _port_free(port):
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def setup_vscode(meta):
    marker = ROOT / "state" / "s10_marker.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("Session 10 Computer-Use skill — Electron page-path marker.\n")
    # An earlier run's editor window may still hold the usual port. Never
    # attach to a port something else owns; move to the next unused one.
    preferred = int(meta["electron_debugging_port"])
    port = next((p for p in range(preferred, preferred + 10) if _port_free(p)), None)
    if port is None:
        return False, f"Debugging ports {preferred}-{preferred + 9} are all occupied; quit earlier editor runs"
    meta["electron_debugging_port"] = port
    candidates = [("Visual Studio Code", "com.microsoft.VSCode"), ("Cursor", "com.todesktop.230313mzl4w4u92")]
    editor = next(((name, bundle) for name, bundle in candidates
                   if Path(f"/Applications/{name}.app").exists()), None)
    if editor is None:
        return False, "Neither VS Code nor Cursor is installed"
    name, bundle = editor
    profile = Path(tempfile.mkdtemp(prefix="s10_electron_", dir=marker.parent))
    launched = get_driver().call("launch_app", {
        "bundle_id": bundle, "electron_debugging_port": port,
        "creates_new_application_instance": True,
        "additional_arguments": [f"--user-data-dir={profile}", "-n", str(marker)],
    })
    meta["app"] = name
    meta["activate"] = False
    _remember_launch(meta, launched)
    time.sleep(3)
    return True, f"Separate {name} profile launched with debugging port {port}"


def setup_canvas(meta):
    state = ROOT / "state"
    state.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix="s10_chrome_", dir=state))
    launched = get_driver().call("launch_app", {
        "bundle_id": "com.google.Chrome", "creates_new_application_instance": True,
        "additional_arguments": [f"--user-data-dir={profile}", "--no-first-run",
                                 "--no-default-browser-check", "--new-window", canvas_url()],
    })
    _remember_launch(meta, launched)
    time.sleep(2)
    return True, "Fresh canvas target opened in a separate Chrome profile"


SETUP = {"calculator": setup_calculator, "vscode": setup_vscode, "canvas": setup_canvas}


async def run_task(name):
    meta = dict(TASKS[name])
    skill = ComputerSkill(trajectories_root=str(TRAJ_ROOT))
    result = await skill.run(NodeSpec(skill="computer", metadata=meta), setup=SETUP[name])
    out = result.output
    record = {"task": name, "success": result.success, "layer": out.get("path"),
              "turns": out.get("turns", 0), "vision_calls": out.get("vision_calls", 0),
              "trajectory_dir": out.get("trajectory_dir"), "error": result.error}
    print(f"  [{'PASS' if result.success else 'FAIL'}] {name}: "
          f"layer={record['layer']} turns={record['turns']} vision_calls={record['vision_calls']}")
    if result.error:
        print(f"    {result.error}")
    return record


def constraints_pass(results):
    successful = [r for r in results if r.get("success")]
    return (len({r["task"] for r in successful}) >= 3
            and any(r.get("vision_calls") == 0 for r in successful)
            and any((r.get("vision_calls") or 0) > 0 for r in successful)
            and any(r.get("layer") == "page" for r in successful))


async def main(argv):
    flags = {"--preflight", "--dry-run"}
    unknown = [arg for arg in argv if arg not in TASKS and arg not in flags]
    if unknown:
        print(f"Unknown arguments: {', '.join(unknown)}")
        return 2
    if "--preflight" in argv and len(argv) != 1:
        print("--preflight must be used on its own")
        return 2
    names = list(dict.fromkeys(arg for arg in argv if arg in TASKS)) or list(TASKS)
    if "--dry-run" in argv:
        print("PLAN ONLY — no daemon, apps, screenshots, permission checks, or model calls")
        for name in names:
            task = TASKS[name]
            print(f"  {name}: {task['goal']}")
        print(f"  Evidence destination: {TRAJ_ROOT}")
        return 0
    if "--preflight" in argv:
        return 0 if print_preflight(preflight()) else 1
    if not print_preflight(preflight()):
        return 1
    results = []
    for name in names:
        try:
            results.append(await run_task(name))
        except Exception as exc:
            results.append({"task": name, "success": False, "error": f"{type(exc).__name__}: {exc}"})
    full_run = set(names) == set(TASKS)
    passed = constraints_pass(results)
    print(f"CONSTRAINTS: {'PASS' if passed else 'INCOMPLETE'}")
    TRAJ_ROOT.mkdir(parents=True, exist_ok=True)
    portable = [{**r, "trajectory_dir": Path(r["trajectory_dir"]).name if r.get("trajectory_dir") else None}
                for r in results]
    # A single-task rerun replaces only its own row; the other tasks' latest
    # results stay, so the evidence check still sees all three.
    summary_path = TRAJ_ROOT / "summary.json"
    try:
        previous = json.loads(summary_path.read_text())
    except (OSError, ValueError):
        previous = []
    kept = [row for row in previous if isinstance(row, dict) and row.get("task") not in names] \
        if isinstance(previous, list) else []
    summary_path.write_text(json.dumps(kept + portable, indent=2))
    return 0 if all(r["success"] for r in results) and (passed or not full_run) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
