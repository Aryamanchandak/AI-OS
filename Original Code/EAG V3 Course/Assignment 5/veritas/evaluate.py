"""Run the prompt-evaluation rubric against v1 and v2 of the master prompt.

This is what qualifies the prompt. Output is written to evaluations/*.json so
EVALUATION.md quotes a real model call rather than an authored transcript.

    python evaluate.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from llm import LLM

ROOT = Path(__file__).parent
OUT = ROOT / "evaluations"

EVALUATOR_PROMPT = """\
You are an expert prompt evaluator. Evaluate the following system prompt
against these nine criteria. For each, answer yes/no/partial and justify in one
sentence. Then return a JSON block with the scores.

1. Explicit Reasoning Instructions - does the prompt tell the model to
   reason step-by-step before answering?
2. Structured Output Format - does it define a clear, parseable output
   structure?
3. Separation of Reasoning and Tools - is thinking separated from tool
   use / action?
4. Conversation Loop Support - can it handle multi-turn or iterative
   interaction?
5. Instructional Framing - does it explain how to behave, with examples
   or clear role definition?
6. Internal Self-Checks - does it instruct the model to verify its own
   output?
7. Reasoning Type Awareness - does it ask the model to identify the KIND
   of reasoning being used?
8. Error Handling / Fallbacks - does it define what to do when things
   fail or are ambiguous?
9. Overall Clarity - is the prompt clear and unambiguous?

Be a demanding grader. Award "yes" only when the prompt operationalizes the
criterion with a concrete mechanism; award "partial" when it gestures at the
criterion without enforcing it; award "no" when it is absent.

Return ONLY this JSON object:
{"scores": {"explicit_reasoning_instructions": "yes|no|partial",
            "structured_output_format": "...",
            "separation_of_reasoning_and_tools": "...",
            "conversation_loop_support": "...",
            "instructional_framing": "...",
            "internal_self_checks": "...",
            "reasoning_type_awareness": "...",
            "error_handling_fallbacks": "...",
            "overall_clarity": "..."},
 "justifications": {"<criterion_name>": "<one sentence>", ...},
 "total_yes": 0,
 "critical_gaps": ["..."],
 "verdict": "..."}
"""

V1 = """\
You are Veritas, a scientific claim verification agent. Given a claim, you
verify it against published literature.

Your skills:
- decompose the claim into sub-claims
- search for evidence
- fetch primary sources
- extract findings
- grade source quality
- synthesize a verdict
- verify your own work

Return a verdict of Supported, Mixed, Refuted, or Insufficient Evidence,
with a confidence score and citations for each claim you make. Be rigorous
and do not make things up. Return your answer as JSON.
"""


def load_v2() -> str:
    text = (ROOT.parent / "PROMPT.md").read_text()
    match = re.search(r"```text\s*(.*?)```", text, re.DOTALL)
    if not match:
        raise SystemExit("no ```text block in PROMPT.md")
    return match.group(1).strip()


def evaluate(llm: LLM, label: str, prompt: str) -> dict:
    print(f"\n  evaluating {label} ({len(prompt.split())} words) ...", flush=True)
    parsed, raw = llm.complete(
        EVALUATOR_PROMPT,
        f"Here is the system prompt to evaluate:\n\n<prompt>\n{prompt}\n</prompt>",
    )
    OUT.mkdir(exist_ok=True)
    (OUT / f"{label}.json").write_text(json.dumps(parsed, indent=2))
    (OUT / f"{label}.raw.txt").write_text(raw)

    scores = parsed.get("scores", {})
    yes = sum(1 for v in scores.values() if str(v).lower() == "yes")
    partial = sum(1 for v in scores.values() if str(v).lower() == "partial")
    print(f"    {yes}/9 yes, {partial} partial  (reported total_yes: "
          f"{parsed.get('total_yes')})")
    for k, v in scores.items():
        print(f"      {str(v):<8} {k}")
    for gap in parsed.get("critical_gaps", []):
        print(f"      GAP: {gap}")
    return parsed


def main() -> int:
    # Thinking and response share this budget. The judge emits 9 scores, 9
    # justifications, gaps and a verdict — 4000 risked truncating the very
    # output EVALUATION.md quotes.
    llm = LLM({"anthropic": "claude-opus-4-8", "openai": "gpt-4o", "max_tokens": 16000})
    print(f"  judge: {llm.provider} / {llm.model}")

    results = {"judge": f"{llm.provider}/{llm.model}",
               "v1": evaluate(llm, "v1", V1),
               "v2": evaluate(llm, "v2", load_v2())}
    (OUT / "summary.json").write_text(json.dumps(results, indent=2))
    print(f"\n  written to {OUT}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
