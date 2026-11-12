"""Trust classification backed by the pairing repository."""

from __future__ import annotations

from typing import Literal, cast

from gateway.security.pairing import PairingStore, get_pairing_store

TrustLevel = Literal["owner_paired", "user_paired", "untrusted"]


def classify(*args: object) -> TrustLevel:
    if len(args) == 3 and isinstance(args[0], PairingStore):
        store, channel, channel_user_id = args
    elif len(args) == 2:
        store = get_pairing_store()
        channel, channel_user_id = args
    else:
        raise TypeError("classify expects (channel, user_id) or (store, channel, user_id)")
    if not isinstance(channel, str) or not isinstance(channel_user_id, str):
        raise TypeError("channel and channel_user_id must be strings")
    record = cast(PairingStore, store).lookup(channel, channel_user_id)
    if record is None:
        return "untrusted"
    return "owner_paired" if record.trust_level == "owner_paired" else "user_paired"
