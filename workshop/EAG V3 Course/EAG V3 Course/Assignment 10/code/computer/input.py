"""Synthetic input — clicks, typing, hotkeys, app activation.

Two mechanisms, chosen per job rather than by preference:

  * Quartz CGEvent for pointer work and single keystrokes. Precise, fast,
    and takes global screen coordinates that line up with ax.py's geometry.
  * AppleScript (`osascript`) for app activation and for `keystroke`/`key
    code` chords. AppleScript owns the reliable "activate this app and wait
    until it is actually frontmost" behaviour, which is fiddly via Quartz.

Layer 2a (deterministic) uses these directly with no model in the loop.
Layers 2b and 3 use the same primitives, differing only in who chooses the
arguments.
"""
from __future__ import annotations

import subprocess
import time

import Quartz


# ── AppleScript ─────────────────────────────────────────────────────────────
def osascript(script: str, *, timeout: float = 20.0) -> tuple[bool, str]:
    """Run AppleScript, returning (ok, stdout-or-stderr)."""
    try:
        p = subprocess.run(["/usr/bin/osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "osascript timed out"
    if p.returncode != 0:
        return False, (p.stderr or "").strip()
    return True, (p.stdout or "").strip()


def activate_app(name: str, *, settle: float = 0.8) -> tuple[bool, str]:
    """Bring an app to the front and wait for it to settle.

    The settle pause is not superstition: AX geometry read immediately after
    activation can still describe the previous window position, which
    produces clicks landing in the wrong place."""
    ok, out = osascript(f'tell application "{name}" to activate')
    if ok:
        time.sleep(settle)
    return ok, out


def launch_app(name: str, *, settle: float = 2.0) -> tuple[bool, str]:
    ok, out = osascript(f'tell application "{name}" to activate')
    if ok:
        time.sleep(settle)
    return ok, out


# ── keyboard ────────────────────────────────────────────────────────────────
# `key code` numbers for keys AppleScript cannot express as characters.
KEY_CODES = {
    "return": 36, "enter": 36, "tab": 48, "space": 49, "delete": 51,
    "escape": 53, "left": 123, "right": 124, "down": 125, "up": 126,
    "equals": 24, "clear": 71,
}

MODIFIERS = {
    "cmd": "command down", "command": "command down",
    "shift": "shift down", "opt": "option down", "option": "option down",
    "ctrl": "control down", "control": "control down",
}


def press_key(key: str, *, modifiers: list[str] | None = None) -> str:
    """Press one key, optionally with modifiers. `key` is either a name from
    KEY_CODES or a literal character."""
    mods = modifiers or []
    using = ""
    if mods:
        parts = [MODIFIERS[m.lower()] for m in mods if m.lower() in MODIFIERS]
        if parts:
            using = f" using {{{', '.join(parts)}}}"
    k = key.lower()
    if k in KEY_CODES:
        script = f'tell application "System Events" to key code {KEY_CODES[k]}{using}'
    else:
        esc = key.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{esc}"{using}'
    ok, err = osascript(script)
    return "ok" if ok else f"error: {err}"


def type_text(text: str) -> str:
    """Type a literal string via System Events."""
    esc = text.replace("\\", "\\\\").replace('"', '\\"')
    ok, err = osascript(
        f'tell application "System Events" to keystroke "{esc}"'
    )
    return "ok" if ok else f"error: {err}"


def press_sequence(keys: list[str], *, gap: float = 0.12) -> str:
    """Press a list of keys in order. This is the Layer-2a workhorse: an
    arithmetic expression is just a key sequence, and nothing about it needs
    a model. The inter-key gap exists because apps that animate their
    buttons (Calculator does) can drop keystrokes delivered faster than
    their event loop drains."""
    for k in keys:
        out = press_key(k)
        if out.startswith("error"):
            return f"error: at key {k!r}: {out}"
        time.sleep(gap)
    return "ok"


# ── pointer ─────────────────────────────────────────────────────────────────
def click(x: int, y: int, *, settle: float = 0.35) -> str:
    """Left-click at a global screen point."""
    try:
        pt = Quartz.CGPointMake(float(x), float(y))
        # Move first: some apps only update hover state on a real move, and
        # a click without one can land on a control that never highlighted.
        for ev_type in (Quartz.kCGEventMouseMoved,):
            ev = Quartz.CGEventCreateMouseEvent(
                None, ev_type, pt, Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.05)
        for ev_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            ev = Quartz.CGEventCreateMouseEvent(
                None, ev_type, pt, Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.04)
        time.sleep(settle)
        return "ok"
    except Exception as e:                               # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"


def drag(from_x: int, from_y: int, to_x: int, to_y: int, *,
         steps: int = 25) -> str:
    """Press, move in increments, release. Interpolation is required — a
    single jump from source to target reads as a teleport and most canvas
    apps will not register it as a stroke."""
    try:
        def post(ev_type, x, y):
            ev = Quartz.CGEventCreateMouseEvent(
                None, ev_type, Quartz.CGPointMake(float(x), float(y)),
                Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

        post(Quartz.kCGEventMouseMoved, from_x, from_y)
        time.sleep(0.05)
        post(Quartz.kCGEventLeftMouseDown, from_x, from_y)
        for i in range(1, steps + 1):
            post(Quartz.kCGEventLeftMouseDragged,
                 from_x + (to_x - from_x) * i / steps,
                 from_y + (to_y - from_y) * i / steps)
            time.sleep(0.012)
        post(Quartz.kCGEventLeftMouseUp, to_x, to_y)
        time.sleep(0.2)
        return "ok"
    except Exception as e:                               # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"


def scroll(direction: str = "down", amount: int = 5) -> str:
    try:
        dy = {"down": -amount, "up": amount}.get(direction, 0)
        dx = {"right": -amount, "left": amount}.get(direction, 0)
        ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine,
                                                  2, dy, dx)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.25)
        return "ok"
    except Exception as e:                               # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"
