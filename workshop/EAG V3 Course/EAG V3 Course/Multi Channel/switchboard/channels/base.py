"""Channel adapter interface.

Every channel implements exactly this. The core never imports a channel SDK,
and a channel never imports the core's triage or action logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from switchboard.models import Channel, NormalizedMessage


class ChannelAdapter(ABC):
    """Inbound + outbound for one channel."""

    channel: Channel

    # -- inbound ------------------------------------------------------------

    @abstractmethod
    async def fetch(self, cursor: str | None) -> tuple[list[NormalizedMessage], str | None]:
        """Return new messages plus the cursor to persist.

        The caller commits the returned cursor only after the messages are
        durably stored, so a crash mid-batch replays rather than skips.
        Push-based channels (WhatsApp, Twilio webhook) return ([], cursor)
        here and deliver via `handle_webhook` instead.
        """

    async def handle_webhook(self, payload: dict[str, Any], headers: dict[str, str]
                             ) -> list[NormalizedMessage]:
        """Convert a verified webhook payload into messages.

        Poll-based channels never implement this. Implementations MUST verify
        the request signature before doing anything else — an unverified
        webhook endpoint is an open door into the action router.
        """
        raise NotImplementedError(f"{self.channel} is not webhook-based")

    # -- outbound -----------------------------------------------------------

    @abstractmethod
    async def send(self, reply_anchor: dict[str, Any], body: str,
                   subject: str | None = None) -> str:
        """Send a reply in-thread. Returns the new channel message id.

        Only ever called after a human approval. Raises on failure so the
        caller can retry with backoff and surface a terminal failure.
        """

    # -- policy -------------------------------------------------------------

    def can_send_freeform(self, reply_anchor: dict[str, Any]) -> bool:
        """Whether an arbitrary reply is allowed right now.

        Exists for WhatsApp, whose Cloud API only permits free-form replies
        inside a ~24h window from the contact's last message; outside it a
        pre-approved template is required. Every other channel is always True.
        """
        return True

    def is_control_plane(self, msg: NormalizedMessage) -> bool:
        """Suppress the system's own control traffic.

        The Telegram approval bot must never ingest your button taps as new
        inbound mail — that loops. Enforced here at the adapter boundary
        rather than in a prompt, because a prompt can be argued out of a rule.
        """
        return False
