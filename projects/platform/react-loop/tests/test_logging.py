"""Logging setup + that the loop actually emits log records."""

import logging
import os
import sys

from react_loop.brain import FakeBrain
from react_loop.config import LoopConfig, ServerConfig
from react_loop.logging_setup import LOGGER_NAME, configure_logging
from react_loop.loop import ReactLoop
from react_loop.mcp_client import MCPClient

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STUB = os.path.join(_REPO, "tests", "stub_server.py")


def test_configure_logging_is_idempotent(monkeypatch):
    logger = logging.getLogger(LOGGER_NAME)
    monkeypatch.setattr(logger, "handlers", [], raising=False)

    configure_logging(level="DEBUG")
    count = len(logger.handlers)
    assert count >= 1
    assert logger.level == logging.DEBUG

    # Second call must not add another handler, but may change the level.
    configure_logging(level="WARNING")
    assert len(logger.handlers) == count
    assert logger.level == logging.WARNING


async def test_loop_emits_log_records(caplog):
    # Attach caplog's handler straight to the react_loop logger so capture works
    # regardless of propagate (configure_logging sets propagate=False).
    rl_logger = logging.getLogger(LOGGER_NAME)
    rl_logger.addHandler(caplog.handler)
    rl_logger.setLevel(logging.INFO)

    cfg = LoopConfig(
        model="fake", api_key="unused",
        server=ServerConfig(command=sys.executable, args=[_STUB], cwd=_REPO),
    )
    brain = FakeBrain([
        '{"thought": "get the time", "tool": "get_time", "tool_input": {}}',
        '{"thought": "done", "final_answer": "it is noon"}',
    ])
    try:
        async with MCPClient(cfg.server) as client:
            await ReactLoop(brain, client, cfg).run("what time is it?")
    finally:
        rl_logger.removeHandler(caplog.handler)

    messages = [r.getMessage() for r in caplog.records]
    assert any("run start" in m for m in messages)
    assert any("tool=get_time" in m for m in messages)
    assert any("stop_reason=final_answer" in m for m in messages)
