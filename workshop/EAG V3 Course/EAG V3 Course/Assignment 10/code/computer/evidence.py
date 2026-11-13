"""Read-only submission check; never starts apps, replays, or calls models."""
from __future__ import annotations
import json
import sys
from pathlib import Path

from .tasks import TASKS
from .input import key_arguments

ROOT = Path(__file__).resolve().parents[2] / "evidence" / "trajectories"
LAYERS = {"calculator": "deterministic", "vscode": "page", "canvas": "vision"}


def check(root=ROOT):
    root = Path(root).resolve()
    errors = []
    try:
        summary = json.loads((root / "summary.json").read_text())
    except (OSError, ValueError) as exc:
        return [f"Missing or unreadable live-run summary: {exc}"]
    if (not isinstance(summary, list) or not all(isinstance(r, dict) for r in summary)
            or sorted(r.get("task", "") for r in summary) != sorted(TASKS)):
        return ["Summary must contain exactly calculator, vscode, and canvas once each"]
    for row in summary:
        task = row["task"]
        try:
            relative = Path(row["trajectory_dir"])
            directory = (root / relative).resolve()
            if relative.is_absolute() or directory == root or root not in directory.parents:
                raise ValueError("Trajectory must be a relative path inside the evidence directory")
            manifest = json.loads((directory / "manifest.json").read_text())
            state = json.loads((directory / "driver_recording_state.json").read_text())
            events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
            if row.get("success") is not True or manifest.get("success") is not True:
                raise ValueError("Live run did not succeed")
            if row.get("layer") != LAYERS[task] or manifest.get("resolved_at_layer") != LAYERS[task]:
                raise ValueError("Task resolved at the wrong layer")
            calls = sum(e.get("kind") == "llm_call" and e.get("layer") == "vision" for e in events)
            if manifest.get("vision_calls") != calls or row.get("vision_calls") != calls:
                raise ValueError("Vision counters disagree with the event log")
            if (task == "canvas" and calls < 1) or (task != "canvas" and calls != 0):
                raise ValueError("Task does not meet its vision-call requirement")
            if row.get("turns") != manifest.get("turns") or manifest.get("turns", 0) < 1:
                raise ValueError("Turn counts are missing or inconsistent")
            if not manifest.get("driver_recording") or not (directory / "driver").is_dir():
                raise ValueError("Native cua-driver trajectory is missing")
            if state.get("enabled") is not False or state.get("last_error"):
                raise ValueError("Native recording was not finalized successfully")
            if task == "calculator":
                turns = sorted((directory / "driver").glob("turn-*/action.json"))
                arguments = [json.loads(p.read_text()).get("arguments", {}) for p in turns]
                recorded_keys = [{"key": a.get("key"), "modifiers": a.get("modifiers", [])} for a in arguments]
                if recorded_keys != [key_arguments(k) for k in TASKS[task]["keys"]]:
                    raise ValueError("Native recording does not contain the Calculator key sequence")
                if not all((p.parent / "screenshot.png").is_file() for p in turns):
                    raise ValueError("Native action screenshots are missing")
                if (directory / "layer_3_vision").exists():
                    raise ValueError("Calculator unexpectedly reached vision")
            elif task == "vscode":
                proof = json.loads((directory / "layer_2c_page/verification.json").read_text())
                if proof.get("active_tab") != "s10_marker.txt":
                    raise ValueError("Electron active-tab proof is missing")
            else:
                proof = json.loads((directory / "layer_3_vision/verification.json").read_text())
                if "CANVAS-GAME: HIT" not in proof.get("actual", "") or proof.get("success") is not True:
                    raise ValueError("Independent canvas title verification failed")
                if not list((directory / "layer_3_vision").glob("turn_*_screen.png")):
                    raise ValueError("Vision screenshots are missing")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{task}: {exc}")
    return errors


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        print("Usage: python -m computer.evidence [trajectory-root]")
        return 2
    errors = check(Path(argv[0]) if argv else ROOT)
    if errors:
        for error in errors:
            print(f"PENDING: {error}")
        return 1
    print("PASS: all three live trajectories meet the submission checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
