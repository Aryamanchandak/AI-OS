#!/usr/bin/env python3
"""CLI entry point.

  python main.py "compare NVDA, AMD and INTC over the last year"
  python main.py --mock --degrade AMD "compare NVDA, AMD and INTC"   # critic fail
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

from agent import tools
from agent.executor import Executor
from agent.llm import build_llm
from agent.planner import Planner
from agent.skills import load_config, load_skills
from agent.state import SessionStore

ROOT = pathlib.Path(__file__).resolve().parent


def approve_code(node, code):
    if not sys.stdin.isatty():
        return False
    print(f"\nGenerated Python for {node.id}; review before it runs:\n{code}")
    return input("Run this code? Type yes: ").strip().lower() == "yes"


def main() -> int:
    ap = argparse.ArgumentParser(description="DAG agent")
    ap.add_argument("query", nargs="*")
    ap.add_argument("--resume", help="Resume the saved execution directory")
    ap.add_argument("--state", help="Save execution checkpoints in this directory")
    ap.add_argument("--pause-after", type=int, help="Pause after this many completed nodes (layer boundary)")
    ap.add_argument("--mock", action="store_true",
                    help="use the scripted planner instead of the API")
    ap.add_argument("--degrade", action="append", default=[], metavar="TICKER",
                    help="force this ticker's retriever to return a short "
                         "series, to exercise the Critic-fail path")
    ap.add_argument("--log", default=None, help="write the run log JSON here")
    args = ap.parse_args()
    if not args.query and not args.resume:
        ap.error("Provide a query or --resume")

    query = " ".join(args.query) if args.query else None
    tools.DEGRADED_TICKERS.update(t.upper() for t in args.degrade)

    config = load_config()
    skills = load_skills(config)
    llm = build_llm(config, mock=args.mock)

    planner = Planner(skills, llm)
    executor = Executor(
        skills=skills,
        llm=llm,
        artifacts_dir=ROOT / "artifacts",
        replan=planner.replan,
        store=SessionStore(args.resume or args.state) if args.resume or args.state else None,
        code_approval=None if args.mock else approve_code,
    )

    print(f"query: {query}")
    if args.degrade:
        print(f"degraded tickers: {sorted(tools.DEGRADED_TICKERS)}")

    t0 = time.perf_counter()
    graph = None if args.resume else planner.plan(query)
    plan_seconds = time.perf_counter() - t0

    print(f"\nplan ({plan_seconds:.2f}s)" + (f" — {len(graph.nodes)} nodes" if graph else " — resuming saved graph"))
    for i, layer in enumerate(graph.layers() if graph else []):
        marks = [f"{n.id}[{n.skill}]" + ("*" if n.critic else "") for n in layer]
        print(f"  layer {i}: {' | '.join(marks)}")
    print("  (* = critic-gated)")

    log = executor.run(graph, query, stop_after=args.pause_after)
    log.planning_seconds = plan_seconds

    print("\n--- execution ---")
    for i, (ids, secs) in enumerate(zip(log.layers, log.layer_seconds)):
        per_node = ", ".join(f"{nid}={log.node_seconds[nid]:.2f}s" for nid in ids)
        if len(ids) > 1:
            total = sum(log.node_seconds[n] for n in ids)
            longest = max(log.node_seconds[n] for n in ids)
            # Parallel iff wall-clock tracks the LONGEST branch, not the sum.
            # Comparing against the sum mislabels layers with lopsided branches.
            verdict = "PARALLEL" if secs < longest * 1.35 + 0.05 else "SERIAL?"
            print(f"  layer {i}: {secs:.2f}s wall  [{per_node}]")
            print(f"           sum of branches={total:.2f}s  longest branch="
                  f"{longest:.2f}s  -> {verdict}")
        else:
            print(f"  layer {i}: {secs:.2f}s wall  [{per_node}]")

    for v in log.critic_verdicts:
        print(f"\ncritic on {v['node']}: {v['verdict'].upper()}"
              + (f" — {v['reason']}" if v["reason"] else ""))
    for r in log.recoveries:
        print(f"recovery: strategy={r['strategy']} "
              f"spliced={r.get('spliced')} rewired={r.get('rewired')}")

    print(f"\ntotal: {log.total_seconds}s over {log.iterations} iteration(s)")
    print("\n--- answer ---")
    print(log.answer)

    log_path = pathlib.Path(args.log) if args.log else \
        ROOT / "logs" / f"run_{int(time.time())}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log.to_json())
    print(f"\nlog: {log_path}")
    return 1 if log.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
