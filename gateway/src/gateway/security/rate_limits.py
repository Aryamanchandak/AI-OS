"""Bounded per-identity sliding-window rate limits."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import threading
import time
from typing import Any


@dataclass
class _Window:
    messages: deque[float] = field(default_factory=deque)
    tool_calls: deque[float] = field(default_factory=deque)


class RateLimiter:
    def __init__(self, default_mpm: int = 30, default_tpm: int = 20) -> None:
        self.default_mpm = default_mpm
        self.default_tpm = default_tpm
        self.per_channel: dict[str, tuple[int, int]] = {}
        self._state: dict[tuple[str, str], _Window] = {}
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def configure(self, document: dict[str, Any]) -> None:
        defaults = ((document.get("defaults") or {}).get("rate_limits") or {})
        self.default_mpm = int(defaults.get("messages_per_minute", self.default_mpm))
        self.default_tpm = int(defaults.get("tool_calls_per_minute", self.default_tpm))
        for name, config in ((document.get("channels") or {}).items()):
            limits = (config or {}).get("rate_limits") or {}
            if limits:
                self.per_channel[str(name)] = (
                    int(limits.get("messages_per_minute", self.default_mpm)),
                    int(limits.get("tool_calls_per_minute", self.default_tpm)),
                )

    # Kept for the moved provider test/harness contract.
    configure_from_yaml = configure

    def check_message(self, channel: str, user_id: str) -> tuple[bool, str]:
        return self._check(channel, user_id, "messages")

    def check_tool_call(self, channel: str, user_id: str) -> tuple[bool, str]:
        return self._check(channel, user_id, "tool_calls")

    def _check(self, channel: str, user_id: str, kind: str) -> tuple[bool, str]:
        mpm, tpm = self.per_channel.get(channel, (self.default_mpm, self.default_tpm))
        cap = mpm if kind == "messages" else tpm
        with self._lock:
            now = time.time()
            if now - self._last_sweep >= 60:
                self._last_sweep = now
                for key, window in list(self._state.items()):
                    self._trim(window.messages, now)
                    self._trim(window.tool_calls, now)
                    if not window.messages and not window.tool_calls:
                        del self._state[key]
            window = self._state.setdefault((channel, user_id), _Window())
            queue = window.messages if kind == "messages" else window.tool_calls
            self._trim(queue, now)
            if len(queue) >= cap:
                return False, f"{kind} limit {cap}/min exceeded for ({channel}, {user_id})"
            queue.append(now)
            return True, ""

    @staticmethod
    def _trim(queue: deque[float], now: float) -> None:
        while queue and queue[0] < now - 60:
            queue.popleft()


_limiter: RateLimiter | None = None


def bind_rate_limiter(limiter: RateLimiter | None) -> None:
    global _limiter
    _limiter = limiter


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        from gateway.channels.setup_config import load_channels

        _limiter = RateLimiter()
        _limiter.configure(load_channels())
    return _limiter
