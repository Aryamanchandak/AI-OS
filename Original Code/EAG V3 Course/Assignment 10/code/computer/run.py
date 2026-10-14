"""Run the three assignment tasks and record their trajectories.

    python -m computer.run              # all three
    python -m computer.run calculator   # one
    python -m computer.run --preflight  # check permissions only

Each task gets whatever environment setup it needs (launching VS Code with
the debugging flag, opening the canvas page) before the skill runs, then the
skill's cascade takes over. Setup lives here rather than in the skill
because "make the world ready" is the harness's job — the skill's job is to
drive whatever it finds.
"""
from __future__ import annotations

import asyncio
import json
import httpx
import subprocess
import sys
import time
from pathlib import Path

from schemas import NodeSpec

from . import input as osinput
from .ax import ax_available
from .cdp import CDPError, list_targets
from .skill import ComputerSkill
from .tasks import TASKS, VSCODE_DEBUG_PORT, canvas_url


ROOT = Path(__file__).resolve().parent.parent
TRAJ_ROOT = ROOT / "state" / "trajectories"


# ── preflight ───────────────────────────────────────────────────────────────
def preflight() -> dict:
    """Report the OS grants the cascade needs. Checked up front because both
    failures are silent at the API level: an ungranted AX read returns an
    empty tree, and an ungranted screen capture returns a desktop-wallpaper
    image — each looks like a bad model rather than a missing permission."""
    checks = {}
    checks["accessibility"] = ax_available()

    try:
        from .screen import capture
        png, scale = capture()
        checks["screen_recording"] = len(png) > 10_000
        checks["display_scale"] = scale
    except Exception as e:                               # noqa: BLE001
        checks["screen_recording"] = False
        checks["screen_error"] = f"{type(e).__name__}: {e}"

    return checks


def print_preflight(checks: dict) -> bool:
    print("Preflight")
    print(f"  Accessibility permission : {'OK' if checks.get('accessibility') else 'MISSING'}")
    print(f"  Screen Recording         : {'OK' if checks.get('screen_recording') else 'MISSING'}")
    if checks.get("display_scale"):
        print(f"  Display scale            : {checks['display_scale']}x")
    ok = checks.get("accessibility") and checks.get("screen_recording")
    if not ok:
        print(
            "\n  Grant these to the app running this script (Terminal / "
            "iTerm / VS Code):\n"
            "    System Settings > Privacy & Security > Accessibility\n"
            "    System Settings > Privacy & Security > Screen Recording\n"
            "  Then restart that app — macOS only re-reads the grant on "
            "process start."
        )
    return bool(ok)


# ── per-task environment setup ──────────────────────────────────────────────
def setup_calculator() -> tuple[bool, str]:
    ok, err = osinput.launch_app("Calculator")
    if not ok:
        return False, f"could not launch Calculator: {err}"
    # Clear any state left by a previous run, so 611 on the display can only
    # have come from this run's key sequence.
    osinput.press_key("escape")
    time.sleep(0.3)
    return True, "Calculator launched and cleared"


def setup_vscode() -> tuple[bool, str]:
    """Launch the Electron editor with the remote debugging port open.

    Two Electron facts drive the shape of this function:

    1. CDP only exists if the process was started with
       `--remote-debugging-port`. You cannot enable it on a running instance.
    2. Launching the binary again while an instance is running normally just
       signals that instance to open a window — the new flags are discarded.

    Passing a distinct `--user-data-dir` defeats (2): Electron treats it as a
    separate instance and genuinely starts a new process with our flags. That
    matters because the alternative is quitting the editor the user is
    working in, which is not an acceptable side effect of running a test."""
    marker = ROOT / "state" / "s10_marker.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        "Session 10 Computer-Use skill — Electron page-path marker file.\n"
        "The vscode task reads this file's name out of the live workbench "
        "DOM over CDP.\n"
    )

    # Synchronous on purpose: setup runs inside the runner's event loop, so
    # asyncio.run() here would raise. A blocking GET is also the honest shape
    # for "wait until the port answers".
    def port_live() -> bool:
        try:
            r = httpx.get(f"http://127.0.0.1:{VSCODE_DEBUG_PORT}/json/list",
                          timeout=2.0)
            return r.status_code == 200
        except Exception:                                # noqa: BLE001
            return False

    if port_live():
        return True, f"CDP already live on {VSCODE_DEBUG_PORT}"

    # Prefer VS Code proper; fall back to Cursor, which is the same
    # workbench and so the same DOM selectors.
    candidates = [
        ("/Applications/Visual Studio Code.app/Contents/MacOS/Electron", "VS Code"),
        ("/Applications/Cursor.app/Contents/MacOS/Cursor", "Cursor"),
    ]
    app, label = next(((p, n) for p, n in candidates if Path(p).exists()),
                      (None, None))
    if not app:
        return False, ("no Electron editor found (looked for VS Code and "
                       "Cursor in /Applications)")

    profile = ROOT / "state" / "s10_electron_profile"
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [app, f"--remote-debugging-port={VSCODE_DEBUG_PORT}",
         f"--user-data-dir={profile}", "-n", str(marker)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        # Detach into its own session. Without this the editor inherits our
        # process group and dies with the shell that started the run — which
        # kills the CDP endpoint the task depends on, intermittently and
        # only after setup has already reported success.
        start_new_session=True,
    )
    # The renderer registers its CDP target a beat after the process starts,
    # and a cold profile is slower still — poll instead of guessing a sleep.
    for _ in range(40):
        time.sleep(1.0)
        if port_live():
            return True, f"{label} launched with CDP on {VSCODE_DEBUG_PORT}"
    return False, f"{label} started but CDP never came up on {VSCODE_DEBUG_PORT}"


def setup_canvas() -> tuple[bool, str]:
    url = canvas_url()
    subprocess.run(["open", "-a", "Google Chrome", url], capture_output=True)
    time.sleep(2.5)
    osinput.activate_app("Google Chrome")
    time.sleep(1.0)
    return True, f"canvas game opened: {url}"


SETUP = {
    "calculator": setup_calculator,
    "vscode": setup_vscode,
    "canvas": setup_canvas,
}


# ── runner ──────────────────────────────────────────────────────────────────
async def run_task(name: str) -> dict:
    meta = dict(TASKS[name])
    print(f"\n{'=' * 68}\nTASK: {name}\n  goal: {meta['goal'][:90]}\n{'=' * 68}")

    setup = SETUP.get(name)
    if setup:
        ok, note = setup()
        print(f"  setup: {note}")
        if not ok:
            return {"task": name, "success": False, "error": f"setup failed: {note}"}

    skill = ComputerSkill(trajectories_root=str(TRAJ_ROOT))
    result = await skill.run(NodeSpec(skill="computer", metadata=meta))

    out = result.output or {}
    print(f"  -> success={result.success} layer={out.get('path')} "
          f"turns={out.get('turns')} vision_calls={out.get('vision_calls', 0)}")
    if result.error:
        print(f"  -> error: {result.error}")
    if out.get("trajectory_dir"):
        print(f"  -> trajectory: {out['trajectory_dir']}")

    return {
        "task": name,
        "success": result.success,
        "layer": out.get("path"),
        "turns": out.get("turns"),
        "vision_calls": out.get("vision_calls", 0),
        "trajectory_dir": out.get("trajectory_dir"),
        "error": result.error,
    }


async def main(argv: list[str]) -> int:
    if "--preflight" in argv:
        return 0 if print_preflight(preflight()) else 1

    names = [a for a in argv if a in TASKS] or list(TASKS)
    checks = preflight()
    print_preflight(checks)

    results = []
    for n in names:
        try:
            results.append(await run_task(n))
        except Exception as e:                           # noqa: BLE001
            print(f"  !! {type(e).__name__}: {e}")
            results.append({"task": n, "success": False,
                            "error": f"{type(e).__name__}: {e}"})

    print(f"\n{'=' * 68}\nSUMMARY")
    for r in results:
        flag = "PASS" if r["success"] else "FAIL"
        print(f"  [{flag}] {r['task']:<11} layer={r.get('layer')} "
              f"vision_calls={r.get('vision_calls')}")

    # The assignment's three constraints, checked against what actually ran
    # rather than against what was intended.
    zero_vision = [r for r in results if r.get("success") and r.get("vision_calls") == 0]
    used_vision = [r for r in results if r.get("success") and (r.get("vision_calls") or 0) > 0]
    used_page = [r for r in results if r.get("success") and r.get("layer") == "page"]
    print("\nCONSTRAINTS")
    print(f"  >=1 task with zero vision calls : "
          f"{'YES — ' + zero_vision[0]['task'] if zero_vision else 'NO'}")
    print(f"  >=1 task using vision           : "
          f"{'YES — ' + used_vision[0]['task'] if used_vision else 'NO'}")
    print(f"  >=1 task on the Electron page   : "
          f"{'YES — ' + used_page[0]['task'] if used_page else 'NO'}")

    TRAJ_ROOT.mkdir(parents=True, exist_ok=True)
    (TRAJ_ROOT / "summary.json").write_text(json.dumps(results, indent=2))
    print(f"\n  trajectories: {TRAJ_ROOT}")
    return 0 if all(r["success"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
