"""Channel adapter layer.

Public surface:
  - envelope.ChannelMessage / ChannelReply / Attachment / TrustLevel
  - base.ChannelAdapter (ABC)
  - registry.discover() / registry.get(name)
"""

from gateway.channels.base import ChannelAdapter
from gateway.channels.envelope import (
    Attachment,
    ChannelError,
    ChannelMessage,
    ChannelReply,
    TrustLevel,
)

__all__ = [
    "Attachment",
    "ChannelError",
    "ChannelAdapter",
    "ChannelMessage",
    "ChannelReply",
    "TrustLevel",
]
