"""Config — the two things README.md keeps *outside* the spine.

    1. The system prompt / persona.
    2. Which MCP server the agent points at.

Both are read from the environment (with defaults) so migrating to the research
agent or a different server is a config change, not a code change. The spine
never hard-codes either.
"""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Secrets live in the shared workspace .env one level up, not in this project.
# Load that first (it holds OPENAI_API_KEY), then let a local ./.env override
# for anything project-specific (model, caps, server target).
_SHARED_ENV = "/Users/aryamanchandak/Documents/AI Code/.env"
load_dotenv(_SHARED_ENV)
load_dotenv(override=False)

# Default target: the bundled `simple_server` in THIS project. It only needs
# `mcp` (already in our venv), so we launch it with our own interpreter — no
# separate environment. The loop is server-agnostic: point it at any other stdio
# MCP server via the MCP_SERVER_* env vars below.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass(frozen=True)
class ServerConfig:
    """How to launch the MCP server as a stdio subprocess."""

    command: str
    args: list[str]
    cwd: str | None = None
    env: dict[str, str] | None = None

    @classmethod
    def from_env(cls) -> "ServerConfig":
        # Command defaults to *our own* interpreter so the bundled server runs in
        # this venv with no extra setup. Override MCP_SERVER_COMMAND to point at
        # any other stdio server (e.g. `node`, `uvx`, a different python).
        command = os.environ.get("MCP_SERVER_COMMAND", sys.executable)
        # Args are one string in the env; shlex.split gives shell-like tokenizing
        # (quotes/spaces handled) so `-m foo --flag "a b"` parses correctly.
        args_env = os.environ.get("MCP_SERVER_ARGS")
        if args_env:
            args = shlex.split(args_env)
        else:
            # Default: launch the bundled `simple_server` package as a module.
            args = ["-m", "simple_server"]
        # cwd matters because `-m simple_server` must resolve from the project
        # root where that package lives; default there unless told otherwise.
        cwd = os.environ.get("MCP_SERVER_CWD", _PROJECT_ROOT)
        return cls(command=command, args=args, cwd=cwd)


@dataclass(frozen=True)
class LoopConfig:
    """Everything tunable about a run. Nothing here is baked into the spine."""

    model: str = "gpt-4o-mini"
    api_key: str | None = None
    # The persona is prepended to the tool listing to form the system prompt. It
    # lives here (not in the spine) so switching the agent's role is config-only.
    persona: str = (
        "You are a careful, methodical research assistant. You accomplish tasks "
        "by selecting and chaining the available tools one step at a time, "
        "reasoning explicitly before each action, and stopping as soon as you can "
        "give a complete, well-supported final answer."
    )
    # Hard cap on think->act cycles: the loop's ultimate stop guarantee so a
    # confused model can't spin forever.
    max_iterations: int = 15
    # How many times we'll re-ask after an unparseable reply before giving up.
    max_repairs: int = 3
    # Ceiling on a single observation's length, so one huge tool output can't
    # crowd out the rest of the context window.
    observation_char_limit: int = 4000
    # field(default_factory=...) so each LoopConfig re-reads the server env at
    # construction rather than freezing it once at class-definition time.
    server: ServerConfig = field(default_factory=ServerConfig.from_env)

    @classmethod
    def from_env(cls) -> "LoopConfig":
        # Every knob has an env override with the same default as the dataclass
        # above; ints are cast explicitly since env values arrive as strings.
        return cls(
            model=os.environ.get("REACT_LOOP_MODEL", "gpt-4o-mini"),
            api_key=os.environ.get("OPENAI_API_KEY"),
            max_iterations=int(os.environ.get("REACT_LOOP_MAX_ITERATIONS", "15")),
            max_repairs=int(os.environ.get("REACT_LOOP_MAX_REPAIRS", "3")),
            observation_char_limit=int(
                os.environ.get("REACT_LOOP_OBS_CHAR_LIMIT", "4000")
            ),
            server=ServerConfig.from_env(),
        )
