"""The three assignment tasks, as NodeSpec metadata.

Each task is a plain dict the ComputerSkill consumes — no task-specific code
paths in the skill itself. That is the point: if a task needed its own
branch inside the cascade, the cascade would not be general.

Constraint coverage (the assignment requires all three):

    calculator  → Layer 2a   zero vision calls
    vscode      → Layer 2c   Electron page path, electron_debugging_port
    canvas      → Layer 3    vision

Each task also carries `expect`, so success is decided by re-reading the
world rather than by the model asserting done().
"""
from __future__ import annotations

from pathlib import Path


TARGETS = Path(__file__).parent / "targets"

# Port for the Electron task. Arbitrary but fixed, so the launch helper and
# the task metadata cannot disagree.
VSCODE_DEBUG_PORT = 9222


TASKS: dict[str, dict] = {

    # ── Task 1 — deterministic hotkeys, ZERO vision ────────────────────────
    # 47 × 13 = 611. Calculator accepts keystrokes directly, so the entire
    # task is a key sequence with no model in the loop at any point. The
    # trajectory for this run must contain no layer_3_vision/ directory.
    "calculator": {
        "task": "calculator",
        "app": "Calculator",
        "goal": "compute 47 * 13 and leave the result on the display",
        "keys": ["4", "7", "*", "1", "3", "="],
        # Read back off the AX display. 611 appearing on screen is the only
        # evidence accepted — a delivered keystroke is not a computed result.
        "expect": "611",
        "settle": 0.8,
    },

    # ── Task 2 — Electron page path over CDP ───────────────────────────────
    # Reads the real DOM of VS Code's renderer through
    # electron_debugging_port instead of walking its (vast, largely unnamed)
    # accessibility tree.
    "vscode": {
        "task": "vscode",
        "app": "Cursor",
        "goal": "read the Cursor workbench DOM and report the active editor tab",
        "electron_debugging_port": VSCODE_DEBUG_PORT,
        "page_hint": "Cursor",
        # Pull the active tab's label straight from the workbench DOM. The
        # selector is VS Code's own stable class for the active tab.
        "page_script": """
            (() => {
              const tab = document.querySelector('.tab.active .label-name')
                       || document.querySelector('.tab.active');
              const title = document.title || '';
              return JSON.stringify({
                active_tab: tab ? tab.textContent.trim() : null,
                title,
                tabs: [...document.querySelectorAll('.tab .label-name')]
                        .map(e => e.textContent.trim()).slice(0, 20),
              });
            })()
        """,
        # The marker file the launcher opens; seeing its name in the DOM
        # proves we read the live renderer, not a stale or wrong target.
        "expect": "s10_marker.txt",
        "activate": False,   # CDP needs no foreground window
    },

    # ── Task 3 — canvas, forces Layer 3 vision ─────────────────────────────
    # The target is painted into a <canvas>, so no accessible element
    # describes it. Layers 1/2a/2b are structurally incapable here; the
    # cascade must escalate.
    "canvas": {
        "task": "canvas",
        "app": "Google Chrome",
        "goal": ("click the orange square on the canvas. It is the orange "
                 "filled square in the upper right area of the dark canvas; "
                 "the grey squares are distractors. Click its centre, then "
                 "verify the canvas reads HIT before declaring done."),
        # No force_path. The cascade is left to escalate on its own — that
        # escalation is the behaviour under test, and pinning the layer would
        # skip exactly what the assignment asks us to demonstrate. Layer 2b
        # is capped low because it cannot succeed here (nothing in the AX
        # tree describes a canvas), so spending 12 turns proving that is
        # waste rather than rigour.
        "max_steps_ax": 3,
        # Verified out-of-band: the page sets its title on a real hit, and
        # AppleScript reads that title without any vision call. So the
        # check is independent of the model that did the clicking.
        "verify_applescript":
            'tell application "Google Chrome" to return title of active tab '
            'of front window',
        "expect_verify": "CANVAS-GAME: HIT",
        "settle": 1.0,
    },
}


def canvas_url() -> str:
    return (TARGETS / "canvas_game.html").resolve().as_uri()
