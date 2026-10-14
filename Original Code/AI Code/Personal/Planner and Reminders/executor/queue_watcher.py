# Version: V2
"""
File watcher for queue.md using watchdog (macOS FSEventsObserver).

Starts as a daemon thread from app.py lifespan.
Fires execute_confirmed() whenever queue.md changes.

Self-trigger guard: execute_confirmed() is a no-op when there are no confirmed items,
so the executor's own status writes (done/failed) cause at most one extra read.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

import queue_manager
from executor.executor import run_execute_confirmed

logger = logging.getLogger(__name__)

QUEUE_PATH = Path(__file__).parent.parent / "queue.md"

# Debounce: ignore rapid successive events (executor writes status back quickly)
_DEBOUNCE_SECS = 0.5


class _QueueHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._pending = False
        self._timer: threading.Timer | None = None

    def on_modified(self, event: FileModifiedEvent) -> None:
        if Path(event.src_path).resolve() != QUEUE_PATH.resolve():
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(_DEBOUNCE_SECS, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        if not queue_manager.has_confirmed():
            return
        logger.info("QueueWatcher: confirmed items found — executing")
        try:
            results = run_execute_confirmed()
            for r in results:
                if r["status"] == "failed":
                    logger.error("Execution failed for %s: %s", r["id"], r.get("error"))
                else:
                    logger.info("Executed %s successfully", r["id"])
        except Exception as e:
            logger.exception("QueueWatcher execution error: %s", e)


class QueueWatcher:
    """Starts and stops the watchdog observer thread."""

    def __init__(self) -> None:
        self._handler = _QueueHandler()
        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            path=str(QUEUE_PATH.parent),
            recursive=False,
        )

    def start(self) -> None:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not QUEUE_PATH.exists():
            QUEUE_PATH.write_text("# Planner Action Queue\n", encoding="utf-8")
        self._observer.start()
        logger.info("QueueWatcher started — watching %s", QUEUE_PATH)

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
        logger.info("QueueWatcher stopped")
