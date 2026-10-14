"""CLI entrypoint. Subcommands expose each layer described in README.md.

    python -m react_loop brain              # Phase 0: confirm text comes back
    python -m react_loop tools              # Phase 1: list the server's tools
    python -m react_loop call <name> [k=v]  # Phase 1: call one tool by hand
    python -m react_loop run "<task>"       # Phase 3/4: run the full loop + trace
    python -m react_loop web                # Run the local web UI
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .brain import OpenAIBrain
from .config import LoopConfig
from .logging_setup import configure_logging
from .loop import ReactLoop
from .mcp_client import MCPClient
from .trace import TraceEntry

# A task that deliberately chains >=2 tools so the trajectory shows real
# iteration rather than a single fixed call. Fits the bundled simple_server
# tools (calculator, get_current_time, text_stats).
DEFAULT_TASK = (
    "What is 12.5% of 4800, and what is the current UTC time? "
    "Give both in your final answer."
)


def _require_key(cfg: LoopConfig) -> None:
    if not cfg.api_key:
        sys.exit(
            "OPENAI_API_KEY is not set. Add it to your environment or a .env "
            "file (see .env.example), then retry."
        )


# --- Phase 0 ------------------------------------------------------------
def cmd_brain(cfg: LoopConfig) -> None:
    _require_key(cfg)
    brain = OpenAIBrain(model=cfg.model, api_key=cfg.api_key)
    reply = brain.think([
        {"role": "system", "content": "You are a terse assistant."},
        {"role": "user", "content": "Reply with exactly: brain online."},
    ])
    print(f"[Phase 0] model={cfg.model}\n{reply}")


# --- Phase 1 ------------------------------------------------------------
async def cmd_tools(cfg: LoopConfig) -> None:
    async with MCPClient(cfg.server) as client:
        tools = await client.list_tools()
        print(f"[Phase 1] {len(tools)} tools discovered:\n")
        for t in tools:
            print(f"  - {t.name}: {t.description.strip()[:80]}")


async def cmd_call(cfg: LoopConfig, name: str, kv: list[str]) -> None:
    args: dict = {}
    for pair in kv:
        k, _, v = pair.partition("=")
        try:
            args[k] = json.loads(v)
        except json.JSONDecodeError:
            args[k] = v
    async with MCPClient(cfg.server) as client:
        result = await client.call_tool(name, args)
        print(f"[Phase 1] {name}({json.dumps(args)}) ->\n{result}")


# --- Phase 3 / 4 --------------------------------------------------------
async def cmd_run(cfg: LoopConfig, task: str, as_json: bool) -> None:
    _require_key(cfg)
    brain = OpenAIBrain(model=cfg.model, api_key=cfg.api_key)

    def live(entry: TraceEntry) -> None:  # stream each step as it happens
        if entry.kind == "action":
            print(f"\033[1;36m[step {entry.step}]\033[0m {entry.thought}")
            print(f"    -> {entry.tool}({json.dumps(entry.tool_input)})")
            obs = (entry.observation or "").replace("\n", "\n       ")
            print(f"    <- {obs[:400]}")
        elif entry.kind == "final":
            print(f"\033[1;32m[step {entry.step}] final:\033[0m {entry.final_answer}")
        elif entry.kind in ("repair", "guard"):
            print(f"\033[1;33m[step {entry.step}] {entry.kind}:\033[0m {entry.note}")

    async with MCPClient(cfg.server) as client:
        loop = ReactLoop(brain, client, cfg, on_entry=live)
        result = await loop.run(task)

    print("\n" + "=" * 72)
    if as_json:
        print(result.trajectory.to_json())
    else:
        print(result.trajectory.render(color=sys.stdout.isatty()))
    print(f"\nstop_reason: {result.stop_reason}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="react_loop", description=__doc__)
    p.add_argument(
        "--log-level",
        default=None,
        help="logging level (DEBUG/INFO/WARNING/...); overrides REACT_LOOP_LOG_LEVEL",
    )
    p.add_argument(
        "--log-file",
        default=None,
        help="also write logs to this file; overrides REACT_LOOP_LOG_FILE",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("brain", help="Phase 0: confirm the brain returns text")
    sub.add_parser("tools", help="Phase 1: list the MCP server's tools")

    pc = sub.add_parser("call", help="Phase 1: call one tool by hand")
    pc.add_argument("name")
    pc.add_argument("kv", nargs="*", help="args as key=value (values JSON-parsed)")

    pr = sub.add_parser("run", help="Phase 3/4: run the full loop + trace")
    pr.add_argument("task", nargs="?", default=DEFAULT_TASK)
    pr.add_argument("--json", action="store_true", help="emit trajectory as JSON")

    pw = sub.add_parser("web", help="run the local FastAPI web UI")
    pw.add_argument("--host", default="127.0.0.1")
    pw.add_argument("--port", type=int, default=8000)
    pw.add_argument("--reload", action="store_true")

    args = p.parse_args(argv)
    configure_logging(level=args.log_level, log_file=args.log_file)
    cfg = LoopConfig.from_env()
    if args.cmd == "brain":
        cmd_brain(cfg)
    elif args.cmd == "tools":
        asyncio.run(cmd_tools(cfg))
    elif args.cmd == "call":
        asyncio.run(cmd_call(cfg, args.name, args.kv))
    elif args.cmd == "run":
        asyncio.run(cmd_run(cfg, args.task, args.json))
    elif args.cmd == "web":
        import uvicorn

        uvicorn.run(
            "react_loop.web:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )


if __name__ == "__main__":
    main()
