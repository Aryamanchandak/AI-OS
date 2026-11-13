#!/usr/bin/env python3
"""Bridge: hand a claim or topic to Veritas's CLI.

For anything beyond a well-formed one-liner, draft it first with the
Constructor page (`streamlit run prompt_plan_workbench/app.py`, then open
the Constructor tab in the sidebar) — the workbench's 9-criterion rubric is
built to grade system prompts, not bare claim/topic strings, so this script
does not run that evaluator. It's a thin pass-through to veritas/cli.py.

    python bridge/send_subject.py "Creatine supplementation improves cognitive performance in sleep-deprived adults"
    python bridge/send_subject.py --topic "How does intermittent fasting affect metabolic health?"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERITAS_ROOT = ROOT.parent / "veritas"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("subject", help="The claim to check, or the topic to explore with --topic.")
    parser.add_argument("--topic", action="store_true", help="Explore as an open topic instead of checking a claim.")
    args = parser.parse_args()

    if len(args.subject) > 500:
        print(
            "Note: long, multi-sentence input — consider drafting it down with the "
            "Constructor page first; Veritas's decompose/scope skill works best on a "
            "tight claim or question, not a paragraph.",
            file=sys.stderr,
        )

    cmd = [sys.executable, "cli.py"]
    if args.topic:
        cmd.append("--topic")
    cmd.append(args.subject)

    return subprocess.run(cmd, cwd=VERITAS_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
