"""Per-channel adapter credentials.

Post-audit hardening: before this module, every adapter Function was given
the exact same token used to authenticate `/v1/control/*` (pairing, kill,
presence) and every channel's WS route (`glc.channels.runner.install_token`,
`glc.config.get_or_create_install_token`). A compromised adapter could
therefore call `POST /v1/control/pair` with `trust_level="owner_paired"`,
then `POST /v1/control/pair/confirm` with the code the same response handed
back, and self-escalate to owner trust over plain HTTP — Leak 3
(`force_pair_owner`) reopened through a different door, and it could just as
easily open a WS connection to a channel it doesn't own. Invariant 4 ("a
credential must work only for one specific tool call") was never actually
built on top of Phase 1's process separation.

This module derives one token per channel from the install token, so the
gateway needs no new secret store (it just recomputes the expected value)
and each adapter, once given only its own derived token, has no way to
compute another channel's token or the raw install token itself (HMAC is
one-way, and the adapter never receives the key).
"""

from __future__ import annotations

import hashlib
import hmac


def derive_channel_token(install_token: str, channel: str) -> str:
    """HMAC-SHA256(install_token, channel), hex-encoded.

    Deterministic and stateless: the gateway can always recompute the
    expected token for any channel name from the install token alone,
    without persisting a per-channel secret store. An adapter holding only
    its own derived token cannot derive any other channel's token, nor the
    install token itself.
    """
    return hmac.new(install_token.encode(), channel.encode(), hashlib.sha256).hexdigest()


def verify_channel_token(install_token: str, channel: str, presented: str | None) -> bool:
    """True iff `presented` is exactly this channel's derived token.

    Does NOT accept the raw install token — that comparison, if an admin/dev
    credential should also be allowed to open the WS, is the caller's
    responsibility (see `glc/routes/channels.py`), kept separate so this
    function answers exactly one question: is this the scoped credential for
    this one channel.
    """
    if not presented:
        return False
    expected = derive_channel_token(install_token, channel)
    return hmac.compare_digest(expected, presented)
