"""Run the exact non-browser Session 5–9 prompts and retain full evidence.

The raw response is the authority. The Markdown is only a readable rendering
of prompt → graph patches → agents/providers → final result.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx


def compact(value, limit: int = 1200):
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"… [{len(value) - limit} chars omitted]"
    if isinstance(value, dict):
        return {key: compact(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [compact(item, limit) for item in value]
    return value


def render_case(case: dict, result: dict, elapsed: float) -> str:
    graph = result.get("graph", {})
    nodes = graph.get("nodes", {})
    lines = [
        f"## {case['id']}", "", "### Prompt", "", "```text", case["prompt"], "```", "",
        f"Status: `{result.get('status')}` · run: `{result.get('run_id')}` · HTTP elapsed: `{elapsed:.2f}s`",
        "", "### Graph and agents", "",
        "| node | agent | skill | state | provider/model |", "|---|---|---|---|---|",
    ]
    for node_id, node in nodes.items():
        metadata = node.get("metadata") or {}
        outcome = node.get("result") or {}
        provider = outcome.get("provider", "")
        model = outcome.get("model", "")
        lines.append(
            f"| `{node_id}` | {metadata.get('agent', node.get('skill', ''))} | "
            f"`{node.get('skill')}` | `{node.get('state')}` | {provider}/{model} |"
        )
    lines.extend(["", "Edges: `" + json.dumps(graph.get("edges", [])) + "`", "", "### Expansion trace", ""])
    for event in result.get("events", []):
        if event.get("kind") in {"run_started", "graph_patched", "task_started", "task_succeeded", "task_failed", "task_cancelled", "run_resumed"}:
            lines.append(
                f"- `{event.get('kind')}`"
                + (f" `{event.get('node_id')}`" if event.get("node_id") else "")
                + f": `{json.dumps(compact(event.get('payload', {}), 300), ensure_ascii=False)}`"
            )
    lines.extend(["", "### Final result", "", result.get("answer") or "*(no answer)*", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8113")
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("benchmark_cases.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmark.md"))
    parser.add_argument("--tenant", default="s13-proof")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    raw, sections = [], ["# S13 full non-browser benchmark", ""]
    with httpx.Client(timeout=900) as client:
        for case in cases:
            started = time.perf_counter()
            response = client.post(args.base_url + "/v1/agent/runs", json={
                "tenant_id": args.tenant,
                "project_id": case["project_id"],
                "user_id": "rohan-proof",
                "prompt": case["prompt"],
            })
            elapsed = time.perf_counter() - started
            response.raise_for_status()
            result = response.json()
            raw.append({"case": case, "elapsed_seconds": elapsed, "response": result})
            sections.append(render_case(case, result, elapsed))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(raw, indent=2, ensure_ascii=False))
    args.output.write_text("\n".join(sections))


if __name__ == "__main__":
    main()
