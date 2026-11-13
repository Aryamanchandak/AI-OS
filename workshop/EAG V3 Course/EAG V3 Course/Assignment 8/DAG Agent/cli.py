"""Comparison CLI; ./compare loads .env before this module is imported."""

import argparse
import json
from pathlib import Path
import sys
import time
import uuid

from agent.comparison_service import run_comparison
from agent.framing import ClarificationNeeded, frame_comparison
from agent.llm import build_llm
from agent.skills import load_config

ROOT = Path(__file__).resolve().parent


def session_path(value):
    given = Path(value)
    return given.resolve() if given.exists() or given.is_absolute() or "/" in value else ROOT / "sessions" / value


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare options using supplied evidence or live research.")
    parser.add_argument("question", nargs="*", help="Natural-language comparison or follow-up (requires provider API key)")
    parser.add_argument("--request", help="YAML/JSON comparison with options, criteria and evidence")
    parser.add_argument("--source", action="append", default=[], help="Source URL or explicit text/Markdown/CSV/JSON path")
    parser.add_argument("--live", action="store_true", help="Extract evidence with the provider model")
    parser.add_argument("--session", help="New run ID or directory")
    parser.add_argument("--resume", help="Resume a saved run ID or directory")
    parser.add_argument("--reuse", help="Reuse evidence snapshots from a previous run")
    parser.add_argument("--follow-up", help="Previous run to revise using a natural-language question")
    parser.add_argument("--prioritise", help="Criterion ID for the conclusion; adds no numerical weights")
    parser.add_argument("--chart", help="Criterion ID for a numerical comparison chart")
    parser.add_argument("--weight", action="append", default=[], metavar="ID=NUMBER")
    parser.add_argument("--exclude", action="append", default=[], metavar="OPTION_ID")
    parser.add_argument("--pause-after", type=int, help="Pause after a completed layer reaches this node count")
    args = parser.parse_args(argv)
    if args.resume and (args.request or args.question or args.follow_up or args.weight or args.exclude or args.prioritise or args.chart):
        parser.error("Resume keeps the saved request; use --reuse for a changed comparison")
    if args.pause_after is not None and args.pause_after <= 0:
        parser.error("--pause-after must be positive")
    if not args.resume and not args.request and not args.question:
        parser.print_help()
        return 2
    directory = session_path(args.resume or args.session or (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]))
    request, llm, live = None, None, args.live
    started = time.perf_counter()
    try:
        if args.resume:
            live = json.loads((directory / "mode.json").read_text())["live"]
        elif args.request:
            path = Path(args.request).resolve()
            request = load_config(path)
            for option in request["options"]:
                for source in option.get("sources", []):
                    if source.get("path"):
                        source["path"] = str((path.parent / source["path"]).resolve())
        else:
            live = True
            llm = build_llm(load_config(), session=directory.name)
            sources = [{"id": f"supplied_{i}", "url" if value.startswith(("http://", "https://")) else "path":
                        value if value.startswith(("http://", "https://")) else str(Path(value).resolve())}
                       for i, value in enumerate(args.source, 1)]
            previous = None
            if args.follow_up:
                previous_path = session_path(args.follow_up)
                previous = json.loads((previous_path / "comparison.json").read_text())["request"]
                args.reuse = args.reuse or args.follow_up
            request = frame_comparison(" ".join(args.question), llm, sources, previous)
        if request:
            if args.chart:
                request["chart"] = args.chart
            if args.prioritise:
                request["prioritise"] = args.prioritise
            for weight in args.weight:
                cid, value = weight.split("=", 1)
                criterion = next((c for c in request["criteria"] if c["id"] == cid), None)
                if criterion is None:
                    raise ValueError("Unknown weight criterion: " + cid)
                criterion["weight"] = float(value)
            if args.exclude:
                unknown = set(args.exclude) - {o["id"] for o in request["options"]}
                if unknown:
                    raise ValueError("Unknown excluded option: " + ", ".join(sorted(unknown)))
                request["options"] = [o for o in request["options"] if o["id"] not in args.exclude]
        if live and llm is None:
            llm = build_llm(load_config(), session=directory.name)
        planning_seconds = time.perf_counter() - started
        result, log = run_comparison(request, directory, llm=llm, live=live,
                                     reuse=session_path(args.reuse) if args.reuse else None,
                                     stop_after=args.pause_after)
        print(log.answer or f"Run {log.status}. Completed work is saved.")
        print(f"\nSession: {directory}")
        print(f"Status: {log.status}; execution: {log.total_seconds:.3f}s; "
              f"this invocation: {time.perf_counter() - started:.3f}s")
        for layer, seconds in zip(log.layers, log.layer_seconds):
            longest = max((log.node_seconds[n] for n in layer), default=0)
            print(f"  {' | '.join(layer)}: wall {seconds:.3f}s, longest branch {longest:.3f}s")
        if log.reused_nodes:
            print("Reused evidence snapshots: " + ", ".join(log.reused_nodes))
        if llm:
            print("Model usage: " + json.dumps(llm.usage))
        if not args.resume:
            log.planning_seconds = planning_seconds
        (directory / "run.json").write_text(log.to_json())
        return 1 if log.status == "failed" else 0
    except ClarificationNeeded as exc:
        print("Clarification needed: " + str(exc), file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print(f"Comparison could not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
