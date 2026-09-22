"""Gateway-owned channel registration, policy boundary, and health model."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import time
from typing import Any, Literal

from gateway.audit import AuditStore
from gateway.channels import registry, setup
from gateway.channels.agent_bridge import S16AgentBridge
from gateway.channels.base import ChannelAdapter
from gateway.channels.envelope import ChannelMessage, ChannelReply
from gateway.channels.worker import WorkerSupervisor
from gateway.platform.service_registry import ServiceRegistry
from gateway.security import Allowlist, PairingStore, RateLimiter

Boundary = Literal["in_process", "worker"]
Health = Literal["healthy", "degraded", "disabled"]

CHANNEL_BOUNDARIES: dict[str, Boundary] = {
    "discord": "worker", "gmail": "worker", "imap": "worker",
    "line": "worker", "local_mic": "worker", "matrix": "worker",
    "signal": "worker", "slack": "in_process", "teams": "in_process",
    "telegram": "worker", "twilio_sms": "in_process", "twilio_voice": "worker",
    "webhook": "in_process", "webui": "in_process", "whatsapp": "in_process",
}

VOICE_PROVIDERS: dict[str, tuple[str, str]] = {
    "stt_gemini_live": ("stt", "gemini_live"),
    "stt_groq_whisper": ("stt", "groq_whisper"),
    "stt_whisper_cpp": ("stt", "whisper_cpp"),
    "tts_cartesia": ("tts", "cartesia"),
    "tts_elevenlabs": ("tts", "elevenlabs"),
    "tts_gemini_live": ("tts", "gemini_live"),
    "tts_kokoro": ("tts", "kokoro"),
    "tts_system_fallback": ("tts", "system_fallback"),
}


class ChannelDisabledError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AdapterPresence:
    name: str
    kind: str
    boundary: Boundary
    health: Health
    enabled: bool
    detail: str | None = None

    def public(self) -> dict[str, object]:
        result: dict[str, object] = {
            "name": self.name,
            "kind": self.kind,
            "boundary": self.boundary,
            "health": self.health,
            "enabled": self.enabled,
        }
        if self.detail:
            result["detail"] = self.detail
        return result


class ChannelService:
    def __init__(
        self,
        *,
        configuration: dict[str, Any],
        pairings: PairingStore,
        limiter: RateLimiter,
        allowlist: Allowlist,
        audit: AuditStore,
        bridge: S16AgentBridge,
        services: ServiceRegistry,
    ) -> None:
        self.configuration = configuration
        self.pairings = pairings
        self.limiter = limiter
        self.allowlist = allowlist
        self.audit = audit
        self.bridge = bridge
        self.services = services
        self.supervisor = WorkerSupervisor()
        self.connected: set[str] = set()
        self._discovery = registry.discover_with_failures()
        self._active_requests = 0
        self._drained = asyncio.Event()
        self._drained.set()
        self._closing = False

    def _channel_enabled(self, name: str) -> bool:
        record = ((self.configuration.get("channels") or {}).get(name) or {})
        return bool(record.get("enabled", False))

    def voice_enabled(self, kind: str, provider: str) -> bool:
        record = (((self.configuration.get("voice") or {}).get(kind) or {}).get(provider) or {})
        return bool(record.get("enabled", False))

    def require_enabled(self, name: str) -> None:
        if not self._channel_enabled(name):
            raise ChannelDisabledError(f"channel '{name}' is disabled")

    def set_enabled(self, name: str, enabled: bool) -> None:
        channels = self.configuration.setdefault("channels", {})
        record = dict(channels.get(name) or {})
        record["enabled"] = enabled
        channels[name] = record

    def presence(self) -> list[dict[str, object]]:
        entries: list[AdapterPresence] = []
        for name, boundary in CHANNEL_BOUNDARIES.items():
            enabled = self._channel_enabled(name)
            failure = self._discovery.failures.get(name)
            health: Health = "disabled"
            detail: str | None = None
            if enabled and failure:
                health, detail = "degraded", failure
            elif enabled and name not in self._discovery.adapters:
                health, detail = "degraded", "adapter is unavailable"
            elif enabled and boundary == "worker":
                try:
                    worker = self.services.get(f"{name}_worker")
                    if not worker.enabled:
                        health, detail = "degraded", "worker service is disabled"
                    else:
                        health, detail = "healthy", f"worker at {worker.url}"
                except KeyError:
                    health, detail = "degraded", "worker address is not registered"
            elif enabled:
                health = "healthy"
            entries.append(AdapterPresence(name, "channel", boundary, health, enabled, detail))
        for name, (kind, provider) in VOICE_PROVIDERS.items():
            enabled = self.voice_enabled(kind, provider)
            entries.append(AdapterPresence(name, f"voice_{kind}", "in_process", "healthy" if enabled else "disabled", enabled))
        return [entry.public() for entry in entries]

    def instantiate(self, name: str) -> ChannelAdapter:
        self.require_enabled(name)
        adapter = self._discovery.adapters.get(name)
        if adapter is None:
            detail = self._discovery.failures.get(name, "adapter is unavailable")
            raise RuntimeError(detail)
        return adapter(config=((self.configuration.get("channels") or {}).get(name) or {}))

    def verified_identity(self, message: ChannelMessage) -> ChannelMessage:
        record = self.pairings.lookup(message.channel, message.channel_user_id)
        trust = record.trust_level if record is not None else "untrusted"
        principal = "installation-owner" if trust == "owner_paired" else f"{message.channel}:{message.channel_user_id}"
        return message.model_copy(update={
            "trust_level": trust,
            "metadata": {**message.metadata, "glc_principal_id": principal},
        })

    async def handle(self, message: ChannelMessage) -> ChannelReply | None:
        if self._closing:
            raise RuntimeError("channel service is shutting down")
        self._active_requests += 1
        self._drained.clear()
        try:
            return await self._handle(message)
        finally:
            self._active_requests -= 1
            if self._active_requests == 0:
                self._drained.set()

    async def _handle(self, message: ChannelMessage) -> ChannelReply | None:
        self.require_enabled(message.channel)
        message = self.verified_identity(message)
        owners = [item.channel_user_id for item in self.pairings.owners(message.channel)]
        config = ((self.configuration.get("channels") or {}).get(message.channel) or {})
        public = bool(config.get("is_public", False) or message.metadata.get("is_public_channel", False))
        tokens = config.get("mention_tokens") or []
        mentioned = (
            any(token and token in (message.text or "") for token in tokens)
            if tokens else bool(message.metadata.get("was_mentioned", False))
        )
        ok, reason = self.allowlist.allowed(
            message.channel, message.channel_user_id, owner_ids=owners,
            is_public_channel=public, was_mentioned=mentioned,
        )
        if not ok:
            self.audit.append(channel=message.channel, channel_user_id=message.channel_user_id,
                              trust_level=message.trust_level, event_type="allowlist_drop",
                              result={"reason": reason})
            return None
        ok, reason = self.limiter.check_message(message.channel, message.channel_user_id)
        if not ok:
            self.audit.append(channel=message.channel, channel_user_id=message.channel_user_id,
                              trust_level=message.trust_level, event_type="rate_limit",
                              result={"reason": reason})
            raise RuntimeError(reason)
        self.audit.append(channel=message.channel, channel_user_id=message.channel_user_id,
                          trust_level=message.trust_level, event_type="inbound_message",
                          params={"text": message.text, "thread_id": message.thread_id})
        return await self.bridge.handle(message)

    async def close(self) -> None:
        self._closing = True
        try:
            await asyncio.wait_for(self._drained.wait(), timeout=10)
        except TimeoutError:
            pass
        await self.supervisor.close()
        await self.bridge.close()
