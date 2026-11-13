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

ROOT = pathlib.Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description="DAG agent")
    ap.add_argument("query", nargs="+")
    ap.add_argument("--mock", action="store_true",
                    help="use the scripted planner instead of the API")
    ap.add_argument("--degrade", action="append", default=[], metavar="TICKER",
                    help="force this ticker's retriever to return a short "
                         "series, to exercise the Critic-fail path")
    ap.add_argument("--log", default=None, help="write the run log JSON here")
    args = ap.parse_args()

    query = " ".join(args.query)
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
    )

    print(f"query: {query}")
    if args.degrade:
        print(f"degraded tickers: {sorted(tools.DEGRADED_TICKERS)}")

    t0 = time.perf_counter()
    graph = planner.plan(query)
    plan_seconds = time.perf_counter() - t0

    print(f"\nplan ({plan_seconds:.2f}s) — {len(graph.nodes)} nodes")
    for i, layer in enumerate(graph.layers()):
        marks = [f"{n.id}[{n.skill}]" + ("*" if n.critic else "") for n in layer]
        print(f"  layer {i}: {' | '.join(marks)}")
    print("  (* = critic-gated)")

    log = executor.run(graph, query)

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
