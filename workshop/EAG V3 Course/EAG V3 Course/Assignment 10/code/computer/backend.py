"""The sole cua-driver boundary. Imports never operate the desktop."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from gateway import ASSIGNMENT_ROOT

RELEASE = "0.5.2"
ARCHIVE_SHA256 = "45bfd3244c4943fb677c83250d8c4323d1c8d0b8ea55045a65bf584bba24cb21"
LOCAL_APP = ASSIGNMENT_ROOT / ".tools" / f"cua-driver-rs-{RELEASE}-darwin-universal" / "CuaDriver.app"
SESSION_TOOLS = {"get_window_state", "click", "type_text", "set_value", "press_key", "hotkey", "scroll", "drag"}

class CuaError(RuntimeError):
    pass

class CuaDriver:
    def __init__(self, *, binary=None, run=None, session=None):
        local = LOCAL_APP / "Contents/MacOS/cua-driver"
        self.binary = str(binary or os.getenv("CUA_DRIVER_PATH") or (local if local.exists() else
                          shutil.which("cua-driver") or Path.home() / ".local/bin/cua-driver"))
        self._run = run or subprocess.run
        self.session = session
        self.target = None

    def command(self, *args, timeout=30):
        try:
            return self._run([self.binary, *args], capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CuaError(f"cua-driver unavailable: {exc}") from exc

    def require_daemon(self):
        if self.command("status").returncode:
            raise CuaError("cua-driver daemon is not running; start CuaDriver.app with --args serve")

    def call(self, tool, args=None):
        self.require_daemon()
        payload = dict(args or {})
        if self.session and tool in SESSION_TOOLS:
            payload["session"] = self.session
        result = self.command("call", tool, json.dumps(payload, allow_nan=False), timeout=60)
        if "in-process" in result.stderr.lower():
            raise CuaError("Driver fell back to in-process execution; restore the daemon before retrying")
        if result.returncode:
            detail = result.stderr.strip() or f"exit {result.returncode}"
            if any(word in detail.lower() for word in ("permission", "accessibility", "screen recording")):
                raise PermissionError(f"{tool}: {detail}")
            raise CuaError(f"{tool}: {detail}")
        raw = result.stdout.strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if isinstance(value, dict) and (value.get("isError") or value.get("is_error")):
            raise CuaError(f"{tool}: driver returned an error")
        return value

    def window_args(self):
        if not self.target:
            raise CuaError("No target window has been bound")
        return {"pid": self.target["pid"], "window_id": self.target["window_id"]}

_ACTIVE = ContextVar("computer_driver", default=None)

def get_driver():
    driver = _ACTIVE.get()
    if driver is None:
        driver = CuaDriver()
        _ACTIVE.set(driver)
    return driver

@contextmanager
def driver_scope(driver):
    token = _ACTIVE.set(driver)
    try:
        yield driver
    finally:
        _ACTIVE.reset(token)
