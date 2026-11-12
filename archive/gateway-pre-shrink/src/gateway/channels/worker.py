"""Cancellation-safe supervision for poller and WebSocket channel workers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import random


WorkerRun = Callable[[asyncio.Event], Awaitable[None]]


@dataclass(slots=True)
class WorkerState:
    name: str
    status: str = "disabled"
    restarts: int = 0
    error: str | None = None


class WorkerSupervisor:
    """Run optional workers with bounded exponential backoff and clean stop."""

    def __init__(self, *, initial_backoff_s: float = 0.25, max_backoff_s: float = 30.0) -> None:
        self.initial_backoff_s = initial_backoff_s
        self.max_backoff_s = max_backoff_s
        self._stop = asyncio.Event()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._states: dict[str, WorkerState] = {}

    def register(self, name: str, run: WorkerRun, *, enabled: bool) -> None:
        state = self._states.setdefault(name, WorkerState(name=name))
        if not enabled:
            state.status = "disabled"
            return
        if name in self._tasks:
            return
        state.status = "starting"
        self._tasks[name] = asyncio.create_task(self._supervise(name, run), name=f"channel:{name}")

    async def _supervise(self, name: str, run: WorkerRun) -> None:
        state = self._states[name]
        backoff = self.initial_backoff_s
        while not self._stop.is_set():
            try:
                state.status = "healthy"
                state.error = None
                await run(self._stop)
                if not self._stop.is_set():
                    raise RuntimeError("worker exited without a shutdown request")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state.status = "degraded"
                state.error = f"{type(exc).__name__}: {exc}"
                state.restarts += 1
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=backoff + random.uniform(0, backoff * 0.2)
                    )
                except TimeoutError:
                    pass
                backoff = min(self.max_backoff_s, backoff * 2)
        state.status = "disabled"

    def state(self, name: str) -> WorkerState | None:
        return self._states.get(name)

    async def close(self) -> None:
        self._stop.set()
        tasks = tuple(self._tasks.values())
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=10)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if not task.cancelled():
                    task.exception()
        self._tasks.clear()
