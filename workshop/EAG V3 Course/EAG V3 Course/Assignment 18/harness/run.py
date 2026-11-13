"""Run the fixed agent configuration on a task and save the raw journal.

    uv run python -m harness.run --all            # 3 tasks x 3 repeats
    uv run python -m harness.run --task t1_isin_check_digit --repeat 1

The journal is written before any score exists. An existing journal is never
overwritten: it is the evidence.
"""
import argparse
import difflib
import hashlib
import json
import platform
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from harness.agent import run_agent
from harness.grader import ROOT, TASKS_DIR, grade, hash_files, load_task, make_workspace
from harness.model import OllamaModel
from harness.tools import Workspace

JOURNALS_DIR = ROOT / "journals"


def load_manifest():
    return json.loads((ROOT / "manifest.json").read_text())


def run_one(task_id, repeat, model=None, journals_dir=JOURNALS_DIR, manifest=None):
    """Run one task once. Returns the journal; saves it if journals_dir is set."""
    fixed = manifest or load_manifest()
    task = load_task(task_id)
    run_id = f"{task_id}-r{repeat}"
    journal_path = Path(journals_dir) / f"{run_id}.json" if journals_dir else None
    if journal_path and journal_path.exists():
        raise FileExistsError(f"{journal_path} already exists; journals are never overwritten")

    seed = fixed["seeds"][repeat - 1]
    if model is None:
        model = OllamaModel(fixed["model"], {**fixed["model_options"], "seed": seed}, fixed["model_think"])

    scratch = Path(tempfile.mkdtemp(prefix="a18-"))
    try:
        root = make_workspace(task, scratch / "repo")
        workspace = Workspace(root, task["protected"], fixed["check_timeout_s"])
        protected_before = hash_files(root, only=task["protected"])
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()

        events, finish, stop_reason = run_agent(
            model, workspace, _system_prompt(fixed), task["prompt"], fixed["max_model_calls"]
        )

        journal = {
            "journal_version": 1,
            "run_id": run_id,
            "manifest": {
                **fixed,
                "task": f"{task['id']}@{task['version']}",
                "task_type": task["type"],
                "task_requires": task["requires"],
                "task_protected": task["protected"],
                "task_hash": _digest(hash_files(task["dir"])),
                "harness_hash": _digest(hash_files(ROOT / "harness")),
                "seed": seed,
                "repeat": repeat,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "started_at": started_at,
            "agent_seconds": round(time.monotonic() - started, 2),
            "events": events,
            "finish": finish,
            "stop_reason": stop_reason,
            "protected_hashes": {"before": protected_before, "after": hash_files(root, only=task["protected"])},
            "final_files": _source_files(root, task["protected"]),
            "final_diff": _diff(task["dir"] / "repo", root, task["protected"]),
            "grader": grade(root, task, fixed["provides_env"], fixed["check_timeout_s"]),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if journal_path:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal_path.write_text(json.dumps(journal, indent=2))
    return journal


def _system_prompt(fixed):
    return fixed["system_prompt"].replace("{max_model_calls}", str(fixed["max_model_calls"]))


def _digest(hashes):
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]


def _source_files(root, protected):
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and relative.parts[0] not in protected and "__pycache__" not in path.parts:
            files[relative.as_posix()] = path.read_text(encoding="utf-8", errors="replace")[:20000]
    return files


def _diff(original_root, final_root, protected):
    before = _source_files(Path(original_root), protected)
    after = _source_files(final_root, protected)
    lines = []
    for name in sorted(set(before) | set(after)):
        lines += difflib.unified_diff(
            before.get(name, "").splitlines(), after.get(name, "").splitlines(),
            "a/" + name, "b/" + name, lineterm="",
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="every task, every repeat in the manifest")
    parser.add_argument("--task")
    parser.add_argument("--repeat", type=int)
    args = parser.parse_args()

    fixed = load_manifest()
    if args.all:
        cells = [(p.name, r) for p in sorted(TASKS_DIR.iterdir()) if p.is_dir() for r in range(1, len(fixed["seeds"]) + 1)]
    elif args.task and args.repeat:
        cells = [(args.task, args.repeat)]
    else:
        parser.error("give --all, or --task and --repeat")

    for task_id, repeat in cells:
        try:
            journal = run_one(task_id, repeat)
        except FileExistsError as error:
            print(f"skip  {task_id}-r{repeat}: {error}")
            continue
        print(f"saved {journal['run_id']}: {len(journal['events'])} model calls, "
              f"{journal['agent_seconds']}s, stopped by {journal['stop_reason']}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
