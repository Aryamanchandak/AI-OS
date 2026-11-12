"""One place to configure logging for the ReAct loop.

The loop, brain, and MCP client use module-level ``logging.getLogger(__name__)``
loggers (all under the ``react_loop`` namespace). This module attaches handlers to
that namespace exactly once. Library modules never configure logging at import
time — only the entrypoints (CLI, web, demo) call :func:`configure_logging`, so
importing the package has no logging side effects.
"""

from __future__ import annotations

import logging
import os
import sys

LOGGER_NAME = "react_loop"
_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str | None = None, log_file: str | None = None) -> logging.Logger:
    """Attach a stderr (and optional file) handler to the ``react_loop`` logger.

    Idempotent: if handlers already exist it only updates the level, so calling it
    from both the CLI and the web app never duplicates log lines. Level resolves
    from the ``level`` arg, then ``REACT_LOOP_LOG_LEVEL``, then ``INFO``. A log file
    resolves from ``log_file`` then ``REACT_LOOP_LOG_FILE``.
    """
    resolved_level = (level or os.getenv("REACT_LOOP_LOG_LEVEL") or "INFO").upper()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(resolved_level)
    # Don't bubble up to the root logger (keeps us out of uvicorn's handlers).
    logger.propagate = False

    if logger.handlers:  # already configured — just honor the (possibly new) level
        return logger

    formatter = logging.Formatter(_DEFAULT_FORMAT)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    target_file = log_file or os.getenv("REACT_LOOP_LOG_FILE")
    if target_file:
        file_handler = logging.FileHandler(target_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
