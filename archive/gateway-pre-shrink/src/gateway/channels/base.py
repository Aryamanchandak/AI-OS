"""ChannelAdapter ABC. Every adapter under gateway/channels/catalogue/<name>/
subclasses this. Two methods: on_message (inbound) and send (outbound).
Both speak the typed envelopes from envelope.py."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from gateway.channels.envelope import ChannelMessage, ChannelReply


class ChannelAdapter(ABC):
    name: str = ""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    async def on_message(self, raw: Any) -> ChannelMessage:
        """Translate a native wire-format event into a ChannelMessage.

        The wire format is channel-specific (Telegram Update, Discord
        gateway dispatch, Slack event payload, ...). The translation
        includes classifying the trust level via
        glc.security.trust_level.classify().
        """
        raise NotImplementedError("Implement on_message in this adapter.")

    @abstractmethod
    async def send(self, reply: ChannelReply) -> Any:
        """Translate a ChannelReply into a native wire-format payload and
        dispatch it. Returns whatever the native API returns (often the
        sent-message id, used for thread bookkeeping)."""
        raise NotImplementedError("Implement send in this adapter.")


@runtime_checkable
class ChannelTransport(Protocol):
    """Injected provider transport; SDK-specific implementations stay local."""

    async def send(self, payload: Any) -> Any: ...


@runtime_checkable
class LongRunningChannel(Protocol):
    """Lifecycle contract used by isolated poller/WebSocket workers."""

    async def run(self) -> None: ...
    async def close(self) -> None: ...
