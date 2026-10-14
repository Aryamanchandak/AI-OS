from __future__ import annotations

import argparse
import json
import sys

from .service import ModelForge
from .web import run_server


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="model-forge", description="Build causal models that emit falsifiable predictions.")
    root.add_argument("--library", help="Flat-file model library directory")
    commands = root.add_subparsers(dest="command", required=True)

    forge = commands.add_parser("forge", help="Construct and hone a model")
    source = forge.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--url")
    source.add_argument("--text")
    source.add_argument("--news", metavar="QUERY")
    forge.add_argument("--name", default="")
    forge.add_argument("--predictions", type=int, default=3)
    forge.add_argument("--transfer-domain", default="")

    commands.add_parser("list", help="List library models")
    show = commands.add_parser("show", help="Print a model record")
    show.add_argument("model")
    hone = commands.add_parser("hone", help="Rerun all adversarial passes")
    hone.add_argument("model"); hone.add_argument("--predictions", type=int, default=3); hone.add_argument("--transfer-domain", default="")
    collide = commands.add_parser("collisions", help="Check one model against the library")
    collide.add_argument("model")
    harden = commands.add_parser("harden", help="Steelman one edge")
    harden.add_argument("model"); harden.add_argument("edge")
    forward = commands.add_parser("run-forward", help="Run predictions against observations")
    forward.add_argument("model"); forward.add_argument("observations")
    watch = commands.add_parser("watch-news", help="Run a model forward against live news")
    watch.add_argument("model"); watch.add_argument("query"); watch.add_argument("--limit", type=int, default=10)
    score = commands.add_parser("score", help="Resolve and calibrate a prediction")
    score.add_argument("model"); score.add_argument("prediction"); score.add_argument("outcome", type=float); score.add_argument("--note", default="")
    serve = commands.add_parser("serve", help="Start the local web workspace")
    serve.add_argument("--host", default="127.0.0.1"); serve.add_argument("--port", type=int, default=8765)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "serve":
        run_server(args.host, args.port, args.library)
        return 0
    forge = ModelForge(args.library)
    try:
        if args.command == "forge":
            options = (args.name, args.predictions, args.transfer_domain)
            result = forge.forge_path(args.file, *options) if args.file else forge.forge_url(args.url, *options) if args.url else forge.forge_news(args.news, *options) if args.news else forge.forge_text(args.text, *options)
        elif args.command == "list": result = forge.list_models()
        elif args.command == "show": result = forge.get(args.model).to_dict()
        elif args.command == "hone": result = forge.hone(args.model, args.predictions, args.transfer_domain)
        elif args.command == "collisions": result = forge.collisions(args.model)
        elif args.command == "harden": result = forge.harden(args.model, args.edge)
        elif args.command == "run-forward": result = forge.run_forward(args.model, args.observations)
        elif args.command == "watch-news": result = forge.run_news(args.model, args.query, args.limit)
        elif args.command == "score": result = forge.score(args.model, args.prediction, args.outcome, args.note)
        else: raise AssertionError(args.command)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, RuntimeError, OSError) as exc:
        print(f"model-forge: {exc}", file=sys.stderr)
        return 2
