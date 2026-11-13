"""Loads tasks and takes the raw observations a score is later built from.

Nothing here decides pass or fail. It records exit codes, output and file
hashes; scorer.py interprets them.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "tasks"
CHECK_COMMAND = ["-m", "unittest", "discover", "-s", "tests"]


def load_task(task_id):
    task_dir = TASKS_DIR / task_id
    task = json.loads((task_dir / "task.json").read_text())
    task["dir"] = task_dir
    return task


def make_workspace(task, destination):
    """Copy the task's starting repository to `destination` (must not exist)."""
    shutil.copytree(task["dir"] / "repo", destination)
    return Path(destination).resolve()


def run_check(cwd, extra_env=None, timeout_s=30):
    """Run the required check in `cwd` with a scrubbed environment."""
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}
    env.update(extra_env or {})
    try:
        done = subprocess.run(
            [sys.executable, *CHECK_COMMAND],
            cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout_s,
        )
        return {"exit_code": done.returncode, "output": (done.stdout + done.stderr)[-4000:], "timed_out": False}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "output": f"timed out after {timeout_s}s", "timed_out": True}


def hash_files(root, only=None, skip=()):
    """sha256 of every file under root (or under the `only` folders)."""
    root = Path(root)
    starts = [root / p for p in only] if only is not None else [root]
    hashes = {}
    for start in starts:
        for path in sorted(start.rglob("*")):
            relative = path.relative_to(root)
            if path.is_file() and "__pycache__" not in path.parts and relative.parts[0] not in skip:
                hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def grade(workspace, task, provided_env=None, timeout_s=30):
    """Observe the repository the agent left behind.

    public_as_left: the visible tests, run on the workspace exactly as left.
    acceptance: the agent's source files, with the protected paths restored
        from the task and the held-out tests added, under the manifest's
        environment. This is the check the outcome field is built from.
    acceptance_with_grader_only_resources: the same, plus resources the
        manifest withholds (only for tasks that declare some).
    """
    workspace = Path(workspace)
    observed = {"public_as_left": run_check(workspace, provided_env, timeout_s)}
    with tempfile.TemporaryDirectory() as scratch:
        graded = Path(scratch) / "graded"
        shutil.copytree(workspace, graded, ignore=shutil.ignore_patterns("__pycache__"))
        for protected in task["protected"]:
            shutil.rmtree(graded / protected, ignore_errors=True)
            shutil.copytree(task["dir"] / "repo" / protected, graded / protected)
        for hidden in (task["dir"] / "hidden").glob("*.py"):
            shutil.copy(hidden, graded / "tests" / hidden.name)
        observed["acceptance"] = run_check(graded, provided_env, timeout_s)
        grader_only = task["dir"] / "grader_only_env.json"
        if grader_only.exists():
            env = {**(provided_env or {}), **json.loads(grader_only.read_text())}
            observed["acceptance_with_grader_only_resources"] = run_check(graded, env, timeout_s)
    return observed
