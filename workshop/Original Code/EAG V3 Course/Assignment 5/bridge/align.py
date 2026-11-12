#!/usr/bin/env python3
"""Bridge: propose workbench-reviewed improvements for a live Veritas prompt file.

Reads a Veritas system prompt (the master prompt or one skill contract),
evaluates it against the Prompt & Plan Workbench's rubric, and writes a
candidate replacement + diff to bridge/out/. It never touches veritas/ or
prompt_plan_workbench/ directly — run apply.py to actually adopt a candidate.

    python bridge/align.py --target master
    python bridge/align.py --target decompose --select all
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
ASSIGNMENT_ROOT = ROOT.parent
WORKBENCH_ROOT = ASSIGNMENT_ROOT / "prompt_plan_workbench"
VERITAS_ROOT = ASSIGNMENT_ROOT / "veritas"
MASTER_PROMPT_PATH = ASSIGNMENT_ROOT / "PROMPT.md"
OUT_DIR = ROOT / "out"

sys.path.insert(0, str(WORKBENCH_ROOT))
from engine import ModelSettings, WorkbenchError, apply_improvements, evaluate_content  # noqa: E402


def _load_skill_specs() -> dict:
    cfg = yaml.safe_load((VERITAS_ROOT / "config.yaml").read_text())
    return {name: spec for name, spec in cfg["skills"].items() if spec.get("kind") == "llm"}


def _target_path(target: str, specs: dict) -> Path:
    if target == "master":
        return MASTER_PROMPT_PATH
    return VERITAS_ROOT / specs[target]["prompt"]


def _extract_master_block(text: str) -> tuple[str, str, str]:
    """Split PROMPT.md into (wrapper-before, fenced prompt, wrapper-after)."""
    match = re.search(r"(```text\s*\n)(.*?)(\n?```)", text, re.DOTALL)
    if not match:
        raise SystemExit(f"No ```text fence found in {MASTER_PROMPT_PATH} — expected format has changed.")
    return text[: match.start(2)], match.group(2), text[match.end(2):]


def _context_for(target: str, specs: dict) -> str:
    base = (
        "Veritas is a multi-step LLM research pipeline (sibling project `veritas/`) that checks "
        "claims or explores topics using PubMed/arXiv evidence. "
    )
    if target == "master":
        return base + (
            "This file, PROMPT.md, is the master system prompt: it is prepended to the system "
            "block of every skill call, with that skill's own contract appended after it. It must "
            "define role, scope, and pipeline-wide behavior — not one step's output format, which "
            "belongs in each skill's own contract file."
        )
    spec = specs[target]
    depends = ", ".join(spec.get("depends_on", [])) or "none (pipeline entry point)"
    reroute = spec.get("can_reroute_to")
    context = base + (
        f"This is the `{target}` skill contract, invoked as ACTIVE_SKILL after Veritas's master "
        f"system prompt (loaded separately — not part of this file). It runs once per orchestrator "
        f"call with a typed JSON payload and must return a single JSON object the orchestrator "
        f"parses programmatically; invalid JSON triggers one automatic retry, not human review. "
        f"Depends on: {depends}."
    )
    if reroute:
        context += f" Can be re-entered via a retry loop from `{reroute}`."
    return context


def main() -> int:
    specs = _load_skill_specs()
    choices = ["master", *sorted(specs)]

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--target", required=True, choices=choices)
    parser.add_argument(
        "--select", choices=["high", "all"], default="high",
        help="Which proposed improvements to apply (default: high-priority only, "
             "matching the workbench UI's default selection).",
    )
    parser.add_argument("--provider", default="auto", choices=["auto", "openai", "anthropic"])
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    path = _target_path(args.target, specs)
    if not path.exists():
        raise SystemExit(f"Target file does not exist: {path}")
    original = path.read_text(encoding="utf-8")

    if args.target == "master":
        prefix, inner, suffix = _extract_master_block(original)
    else:
        prefix, inner, suffix = "", original, ""

    settings = ModelSettings(provider=args.provider, model=args.model, api_key=args.api_key)
    context = _context_for(args.target, specs)

    print(f"Evaluating {args.target} ({path.relative_to(ASSIGNMENT_ROOT)})...")
    try:
        evaluation = evaluate_content(inner, context, "prompt", settings)
    except WorkbenchError as exc:
        raise SystemExit(f"Evaluation failed: {exc}")

    print(f"  score {evaluation['score']} · {evaluation['verdict']}")
    for c in evaluation["criteria"]:
        if c["status"] != "yes":
            print(f"  [{c['status']}] {c['label']}: {c['evidence'][:100]}")

    selected = [
        item for item in evaluation["improvements"]
        if args.select == "all" or item["priority"] == "high"
    ]

    OUT_DIR.mkdir(exist_ok=True)
    eval_path = OUT_DIR / f"{args.target}.evaluation.json"
    eval_path.write_text(json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8")

    if not selected:
        print(f"\nNo {args.select}-priority improvements proposed. Full evaluation: {eval_path}")
        return 0

    print(f"\nApplying {len(selected)} {args.select}-priority improvement(s)...")
    try:
        revision = apply_improvements(inner, context, "prompt", selected, settings)
    except WorkbenchError as exc:
        raise SystemExit(f"Revision failed: {exc}")

    new_inner = revision["revised_content"].strip()
    # `suffix` already carries the newline that precedes the closing fence
    # (captured by the `_extract_master_block` regex), so no extra "\n" here.
    candidate_text = f"{prefix}{new_inner}{suffix}" if args.target == "master" else f"{new_inner}\n"

    candidate_path = OUT_DIR / f"{args.target}.candidate.md"
    candidate_path.write_text(candidate_text, encoding="utf-8")

    diff_path = OUT_DIR / f"{args.target}.diff"
    diff = "\n".join(difflib.unified_diff(
        original.splitlines(), candidate_text.splitlines(),
        fromfile=str(path.relative_to(ASSIGNMENT_ROOT)), tofile=f"{args.target} (candidate)", lineterm="",
    ))
    diff_path.write_text(diff, encoding="utf-8")

    print(f"\nCandidate:   {candidate_path}")
    print(f"Diff:        {diff_path}")
    print(f"Evaluation:  {eval_path}")
    print(f"\nReview it, then run: python bridge/apply.py --target {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
