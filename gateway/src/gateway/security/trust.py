"""Trust classification backed by the pairing repository."""

from __future__ import annotations

from typing import Literal

from gateway.security.pairing import PairingStore

TrustLevel = Literal["owner_paired", "user_paired", "untrusted"]


def classify(store: PairingStore, channel: str, channel_user_id: str) -> TrustLevel:
    record = store.lookup(channel, channel_user_id)
    if record is None:
        return "untrusted"
    return "owner_paired" if record.trust_level == "owner_paired" else "user_paired"
