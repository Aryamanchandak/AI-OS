"""Per-channel allowlist evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class Allowlist:
    def __init__(self, configuration: Mapping[str, Any]) -> None:
        self.configuration = configuration

    def allowed(
        self,
        channel: str,
        channel_user_id: str,
        *,
        owner_ids: list[str] | None = None,
        is_public_channel: bool = False,
        was_mentioned: bool = False,
    ) -> tuple[bool, str]:
        defaults = self.configuration.get("defaults") or {}
        channels = self.configuration.get("channels") or {}
        channel_config = channels.get(channel) or {}
        enabled = channel_config.get("enabled", True)
        mention_only = channel_config.get(
            "mention_only_in_public", defaults.get("mention_only_in_public", True)
        )
        allowed_senders = channel_config.get(
            "allowed_senders", defaults.get("allowed_senders", [])
        ) or []
        if not enabled:
            return False, f"channel '{channel}' is disabled in channels.yaml"
        if channel_user_id in (owner_ids or []):
            if is_public_channel and mention_only and not was_mentioned:
                return False, "owner in public channel must be explicitly mentioned"
            return True, ""
        if channel_user_id not in allowed_senders:
            return False, f"sender {channel_user_id!r} not in allowed_senders for '{channel}'"
        if is_public_channel and mention_only and not was_mentioned:
            return False, "sender in public channel must be explicitly mentioned"
        return True, ""
