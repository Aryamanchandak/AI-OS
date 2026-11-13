"""Existing input interface backed by cua-driver; AppleScript only activates apps."""
from __future__ import annotations
import subprocess
import time
from pathlib import Path
import yaml
from .backend import get_driver

KEY_ALIASES = yaml.safe_load(Path(__file__).with_name("keys.yaml").read_text())

def key_arguments(key, modifiers=None):
    alias = KEY_ALIASES.get(key, {"key": key, "modifiers": []})
    return {"key": alias["key"], "modifiers": list(dict.fromkeys([*alias["modifiers"], *(modifiers or [])]))}

def osascript(script, *, timeout=20):
    try:
        result = subprocess.run(["/usr/bin/osascript", "-e", script],
                                capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, (result.stdout if not result.returncode else result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)

def activate_app(name, *, settle=0.8, pid=None):
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    script = (f'tell application "System Events" to set frontmost of '
              f'(first application process whose unix id is {int(pid)}) to true'
              if pid else f'tell application "{escaped}" to activate')
    ok, detail = osascript(script)
    if ok:
        time.sleep(settle)
    return ok, detail

def launch_app(name, **kwargs):
    return get_driver().call("launch_app", {"name": name, **kwargs})

def press_key(key, *, modifiers=None):
    driver = get_driver()
    driver.call("press_key", {**driver.window_args(), **key_arguments(key, modifiers)})
    return "ok"

def press_sequence(keys, *, gap=0.12):
    for key in keys:
        press_key(str(key))
        time.sleep(gap)
    return "ok"

def type_text(text, *, element_index=None):
    driver = get_driver()
    args = {**driver.window_args(), "text": text}
    if element_index is not None:
        args["element_index"] = element_index
    driver.call("type_text", args)
    return "ok"

def click(x, y):
    driver = get_driver()
    driver.call("click", {**driver.window_args(), "x": x, "y": y})
    return "ok"

def drag(from_x, from_y, to_x, to_y):
    driver = get_driver()
    driver.call("drag", {**driver.window_args(), "from_x": from_x, "from_y": from_y,
                         "to_x": to_x, "to_y": to_y})
    return "ok"

def scroll(direction="down", amount=5):
    driver = get_driver()
    driver.call("scroll", {**driver.window_args(), "direction": direction, "amount": amount})
    return "ok"
