#!/usr/bin/env python3
"""Bridge: adopt a reviewed align.py candidate as the live Veritas prompt file.

Backs up the current file (name.bak.<timestamp>) before overwriting, so
every apply is a one-command revert.

    python bridge/apply.py --target master
    python bridge/apply.py --target decompose
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
ASSIGNMENT_ROOT = ROOT.parent
VERITAS_ROOT = ASSIGNMENT_ROOT / "veritas"
MASTER_PROMPT_PATH = ASSIGNMENT_ROOT / "PROMPT.md"
OUT_DIR = ROOT / "out"


def _target_path(target: str) -> Path:
    if target == "master":
        return MASTER_PROMPT_PATH
    cfg = yaml.safe_load((VERITAS_ROOT / "config.yaml").read_text())
    spec = cfg["skills"].get(target)
    if not spec or spec.get("kind") != "llm":
        raise SystemExit(f"Unknown or non-prompt target: {target}")
    return VERITAS_ROOT / spec["prompt"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    candidate_path = OUT_DIR / f"{args.target}.candidate.md"
    if not candidate_path.exists():
        raise SystemExit(f"No candidate found at {candidate_path}. Run align.py --target {args.target} first.")

    live_path = _target_path(args.target)
    if not live_path.exists():
        raise SystemExit(f"Live target does not exist: {live_path}")

    backup_path = live_path.with_name(f"{live_path.name}.bak.{int(time.time())}")
    backup_path.write_text(live_path.read_text(encoding="utf-8"), encoding="utf-8")
    live_path.write_text(candidate_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Applied {candidate_path} -> {live_path}")
    print(f"Backup saved at {backup_path}")
    print(f'Revert with: cp "{backup_path}" "{live_path}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
