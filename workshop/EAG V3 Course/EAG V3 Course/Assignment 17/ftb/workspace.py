"""The isolated folder the engine builds in, and the check this app runs itself.

The engine is started with S17_WORKSPACE pointing here and may edit nothing
else. Before each build the folder is rebuilt from the agreed sheet. After the
build this app re-runs the check on its own: the engine saying "it passes" is
a claim, the exit code we observe is the result.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

MARKER = ".ftb-workspace"
CHECK_COMMAND = "node checks/check_tool.js index.html"
PROTECTED = ("checks/check_tool.js", "checks/cases.json", "SPEC.md")
_ASSET = Path(__file__).parent / "assets" / "check_tool.js"


class WorkspaceError(RuntimeError):
    pass


def prepare(root: Path, *, spec_markdown: str, cases: dict, previous_page: str | None) -> dict[str, str]:
    """Rebuild the workspace for one build. Returns the protected files' fingerprints."""
    if root.exists() and any(root.iterdir()) and not (root / MARKER).exists():
        # Never empty a folder this app did not create.
        raise WorkspaceError(f"{root} is not empty and was not created by this app; refusing to clear it")
    if root.exists():
        shutil.rmtree(root)
    (root / "checks").mkdir(parents=True)
    (root / MARKER).write_text("Created by Financial Tool Builder. Rebuilt before every build.\n")
    (root / ".gitignore").write_text(MARKER + "\n")
    shutil.copyfile(_ASSET, root / "checks" / "check_tool.js")
    (root / "checks" / "cases.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    (root / "SPEC.md").write_text(spec_markdown, encoding="utf-8")
    if previous_page is not None:
        (root / "index.html").write_text(previous_page, encoding="utf-8")
    # Its own repository, so the engine's git commands can never see a parent one.
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=ftb", "-c", "user.email=ftb@localhost", "commit", "-q", "-m", "baseline"]):
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=30)
        if done.returncode != 0:
            raise WorkspaceError(f"git {args[0]} failed in the workspace: {done.stderr.strip()[:300]}")
    return fingerprints(root)


def fingerprints(root: Path) -> dict[str, str]:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() if (root / name).is_file() else "missing"
            for name in PROTECTED}


def verify(root: Path, expected: dict[str, str]) -> dict:
    """Run the protected check ourselves, bounded, and report exactly what it printed."""
    tampered = sorted(name for name, digest in fingerprints(root).items() if digest != expected.get(name))
    if tampered:
        return {"passed": False, "exit_code": None, "command": CHECK_COMMAND, "output": "",
                "reason": "protected files changed during the build: " + ", ".join(tampered)}
    if not (root / "index.html").is_file():
        return {"passed": False, "exit_code": None, "command": CHECK_COMMAND, "output": "",
                "reason": "the engine did not produce index.html"}
    started = time.monotonic()
    root = root.resolve()
    try:
        # No shell, only PATH inherited, read-only access to the workspace alone, on a clock.
        done = subprocess.run(
            ["node", "--permission", f"--allow-fs-read={root}", "checks/check_tool.js", "index.html"],
            cwd=root, capture_output=True, text=True, timeout=30,
            env={"PATH": os.environ.get("PATH", ""), "HOME": str(root)},
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "exit_code": None, "command": CHECK_COMMAND, "output": "",
                "reason": "the check did not finish within 30 seconds"}
    except FileNotFoundError:
        return {"passed": False, "exit_code": None, "command": CHECK_COMMAND, "output": "",
                "reason": "node is not installed, so the check could not run"}
    output = (done.stdout + done.stderr)[-6_000:]
    return {"passed": done.returncode == 0, "exit_code": done.returncode, "command": CHECK_COMMAND,
            "output": output, "seconds": round(time.monotonic() - started, 2),
            "reason": "" if done.returncode == 0 else "the check fails on the page the engine produced"}
