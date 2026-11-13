from __future__ import annotations

import threading
import time
from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class UsageSnapshot:
    calls: int
    input_tokens: int
    output_tokens: int
    elapsed_seconds: float
    max_calls: int
    max_wall_time_seconds: int
    searches: int = 0
    max_searches: int = 0


class UsageLedger:
    def __init__(self, max_calls: int, max_wall_time_seconds: int, max_searches: int | None = None):
        self.max_calls = max_calls
        self.max_wall_time_seconds = max_wall_time_seconds
        # Grounded search hits the same API but is capped separately: counting
        # it against the generation budget starves the pipeline of the calls it
        # needs to finish, because one run issues far more searches than
        # generations.
        self.max_searches = max_calls if max_searches is None else max_searches
        self.started = time.monotonic()
        self._lock = threading.Lock()
        self._calls = self._searches = self._input = self._output = 0

    def guard_external_call(self, kind: str = "model") -> None:
        with self._lock:
            elapsed = time.monotonic() - self.started
            if elapsed >= self.max_wall_time_seconds:
                raise BudgetExceeded("wall-clock budget exceeded")
            if kind == "search":
                if self._searches >= self.max_searches:
                    raise BudgetExceeded("search-call budget exceeded")
                self._searches += 1
                return
            if self._calls >= self.max_calls:
                raise BudgetExceeded("model-call budget exceeded")
            self._calls += 1

    def guard_time(self) -> None:
        if time.monotonic() - self.started >= self.max_wall_time_seconds:
            raise BudgetExceeded("wall-clock budget exceeded")

    def record(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        with self._lock:
            self._input += input_tokens
            self._output += output_tokens

    def snapshot(self) -> UsageSnapshot:
        with self._lock:
            return UsageSnapshot(self._calls, self._input, self._output, round(time.monotonic() - self.started, 3), self.max_calls, self.max_wall_time_seconds, self._searches, self.max_searches)

