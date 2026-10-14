"""Offline end-to-end demo — the whole loop, no OpenAI key, no heavy server.

Drives the real MCPClient + parser + guards + trace + controller against the
stub MCP server, using a FakeBrain scripted to (1) fumble once with bad JSON,
(2) recover, (3) chain two tools, (4) finish. It exercises the repair path AND
a real multi-step tool chain, then prints the Phase-4 trajectory a grader reads.

    uv run python examples/demo_offline.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from react_loop.brain import FakeBrain
from react_loop.config import LoopConfig, ServerConfig
from react_loop.logging_setup import configure_logging
from react_loop.loop import ReactLoop
from react_loop.mcp_client import MCPClient

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STUB = os.path.join(_REPO, "tests", "stub_server.py")

SCRIPT = [
    # 1) The model fumbles: prose instead of JSON -> triggers the repair path.
    "First I'll check the current time, then convert the currency.",
    # 2) Recovers with a valid tool call.
    '{"thought": "Get the current UTC time.", "tool": "get_time", "tool_input": {}}',
    # 3) Chains a second tool using the schema.
    '{"thought": "Now convert 100 USD to EUR.", "tool": "currency_convert",'
    ' "tool_input": {"amount": 100, "from_currency": "USD", "to_currency": "EUR"}}',
    # 4) Finishes.
    '{"thought": "I have both facts and can answer.",'
    ' "final_answer": "The current UTC time is 2026-07-04T12:00:00Z, and 100 USD'
    ' is 90.0 EUR."}',
]


async def main() -> None:
    configure_logging()
    cfg = LoopConfig(
        model="fake", api_key="unused",
        server=ServerConfig(command=sys.executable, args=[_STUB], cwd=_REPO),
    )
    brain = FakeBrain(SCRIPT)
    task = ("What is the current UTC time, and what is 100 USD worth in EUR? "
            "Give both in your final answer.")

    async with MCPClient(cfg.server) as client:
        result = await ReactLoop(brain, client, cfg).run(task)

    rendered = result.trajectory.render(color=sys.stdout.isatty())
    print(rendered)
    print(f"\nstop_reason: {result.stop_reason}")

    # Persist a plain (uncolored) copy as the submittable Phase-4 artifact.
    out = os.path.join(_REPO, "examples", "sample_trajectory.txt")
    with open(out, "w") as f:
        f.write(result.trajectory.render(color=False))
        f.write(f"\n\nstop_reason: {result.stop_reason}\n")
    print(f"\n[saved plain trace -> {out}]")


if __name__ == "__main__":
    asyncio.run(main())
