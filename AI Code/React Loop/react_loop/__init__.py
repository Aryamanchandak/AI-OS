"""A hand-built ReAct loop.

The reasoning brain (OpenAI) only ever returns *text*. This package does the
tool-calling and iteration itself: render tools as text, ask the brain for a
decision, parse it, execute the tool via MCP, feed the observation back, repeat.

Component map (see README.md, "The spine vs. the throwaway shell"):
    3.1 Brain interface ............. brain.py          (spine)
    3.2 MCP client .................. mcp_client.py      (spine)
    3.3 Tool renderer ............... tool_renderer.py   (spine, pure fn)
    3.4 Action contract + parser .... parser.py          (spine)
    3.5 Message list ................ managed in loop.py  (spine)
    3.6 Loop controller ............. loop.py            (THROWAWAY -> PDMA)
    3.7 Guards ...................... guards.py           (spine)
    3.8 Trajectory trace ............ trace.py            (spine)

Isolated to config (never in the spine): system prompt/persona + which MCP
server the agent points at -> config.py.
"""

from .brain import Brain, OpenAIBrain, FakeBrain
from .loop import ReactLoop, LoopResult

__all__ = ["Brain", "OpenAIBrain", "FakeBrain", "ReactLoop", "LoopResult"]
