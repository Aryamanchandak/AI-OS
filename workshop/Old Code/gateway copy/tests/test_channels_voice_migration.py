from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from pathlib import Path
import stat

import pytest

from gateway.audit import AuditStore
from gateway.channels.catalogue.twilio_sms.webhook import compute_signature, validate_signature
from gateway.channels import setup
from gateway.channels.envelope import ChannelMessage, ChannelReply
from gateway.channels.service import CHANNEL_BOUNDARIES, VOICE_PROVIDERS, ChannelService
from gateway.channels.worker import WorkerSupervisor
from gateway.platform.service_registry import ServiceDefinition, ServiceRegistry
from gateway.security import Allowlist, PairingStore, RateLimiter
from gateway.voice.routes import TranscribeRequest, transcribe_route
from gateway.voice.stt.base import STTProvider, TranscribeResult
from gateway.voice.stt.router import register_test_provider


class _Bridge:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = False

    async def handle(self, message: ChannelMessage) -> ChannelReply:
        self.entered.set()
        await self.release.wait()
        return ChannelReply(
            channel=message.channel,
            channel_user_id=message.channel_user_id,
            text="ok",
        )

    async def close(self) -> None:
        self.closed = True


def _service(tmp_path: Path, configuration: dict, bridge: _Bridge | None = None) -> ChannelService:
    limiter = RateLimiter()
    limiter.configure(configuration)
    return ChannelService(
        configuration=configuration,
        pairings=PairingStore(tmp_path / "pairings.sqlite"),
        limiter=limiter,
        allowlist=Allowlist(configuration),
        audit=AuditStore(tmp_path / "audit.sqlite"),
        bridge=bridge or _Bridge(),  # type: ignore[arg-type]
        services=ServiceRegistry({
            "gateway": ServiceDefinition(host="127.0.0.1", port=8000),
            "telegram_worker": ServiceDefinition(
                host="127.0.0.1", port=8121, enabled=False, required=False
            ),
        }),
    )


def test_every_channel_and_voice_adapter_is_registered_dormant(tmp_path: Path) -> None:
    configuration = {
        "defaults": {"allowed_senders": []},
        "channels": {name: {"enabled": False} for name in CHANNEL_BOUNDARIES},
        "voice": {
            "stt": {provider: {"enabled": False} for kind, provider in VOICE_PROVIDERS.values() if kind == "stt"},
            "tts": {provider: {"enabled": False} for kind, provider in VOICE_PROVIDERS.values() if kind == "tts"},
        },
    }
    presence = _service(tmp_path, configuration).presence()
    assert len(presence) == 23
    assert {item["name"] for item in presence} == set(CHANNEL_BOUNDARIES) | set(VOICE_PROVIDERS)
    assert all(item["enabled"] is False and item["health"] == "disabled" for item in presence)


def test_twilio_signature_rejects_tampered_payload() -> None:
    url = "https://gateway.example/webhooks/twilio_sms"
    token = "test-auth-token"
    original = {"From": "+15550001", "Body": "hello"}
    signature = compute_signature(token, url, original)
    assert validate_signature(token, url, original, signature)
    assert not validate_signature(token, url, {**original, "Body": "tampered"}, signature)


def test_channel_admin_never_returns_stored_credentials(monkeypatch, tmp_path: Path) -> None:
    import gateway.channels.setup_config as setup_config

    monkeypatch.setattr(setup_config, "SECRET_ROOT", tmp_path / "channel_secrets")
    secret = "do-not-return-this-token"
    setup.update("telegram", {"TELEGRAM_BOT_TOKEN": secret}, enabled=True)
    public = setup.public_catalogue("https://gateway.example", ["telegram"])
    assert public[0]["enabled"] is True
    assert public[0]["fields"][0]["configured"] is True
    assert secret not in repr(public)
    provider_file = tmp_path / "channel_secrets" / "telegram.json"
    assert provider_file.exists()
    assert stat.S_IMODE(provider_file.stat().st_mode) == 0o600
    assert not (tmp_path / "channel_secrets" / "twilio_sms.json").exists()


@pytest.mark.anyio
async def test_supervisor_stops_during_active_poll() -> None:
    supervisor = WorkerSupervisor(initial_backoff_s=0.001, max_backoff_s=0.01)
    entered = asyncio.Event()
    cleaned_up = asyncio.Event()

    async def poll(stop: asyncio.Event) -> None:
        entered.set()
        try:
            await stop.wait()
        finally:
            cleaned_up.set()

    supervisor.register("telegram", poll, enabled=True)
    await asyncio.wait_for(entered.wait(), timeout=1)
    await supervisor.close()
    assert cleaned_up.is_set()


@pytest.mark.anyio
async def test_channel_service_drains_active_webhook_before_shutdown(tmp_path: Path) -> None:
    bridge = _Bridge()
    configuration = {
        "defaults": {"allowed_senders": []},
        "channels": {"webhook": {"enabled": True}},
    }
    service = _service(tmp_path, configuration, bridge)
    service.pairings.force_pair_owner("webhook", "owner")
    message = ChannelMessage(
        channel="webhook",
        channel_user_id="owner",
        user_handle="owner",
        text="in flight",
        trust_level="untrusted",
        arrived_at=datetime.now(UTC),
    )
    request = asyncio.create_task(service.handle(message))
    await asyncio.wait_for(bridge.entered.wait(), timeout=1)
    shutdown = asyncio.create_task(service.close())
    await asyncio.sleep(0)
    assert not shutdown.done()
    bridge.release.set()
    assert (await request).text == "ok"  # type: ignore[union-attr]
    await shutdown
    assert bridge.closed


class _STT(STTProvider):
    name = "groq_whisper"

    async def transcribe(self, audio: bytes, mime: str) -> TranscribeResult:
        return TranscribeResult("hello", "en", 25, self.name, 0.0)


@pytest.mark.anyio
async def test_transcribe_route_preserves_response_shape_when_explicitly_enabled(tmp_path: Path) -> None:
    configuration = {
        "defaults": {}, "channels": {},
        "voice": {"stt": {"groq_whisper": {"enabled": True}}, "tts": {}},
    }
    service = _service(tmp_path, configuration)
    register_test_provider("groq_whisper", _STT())
    try:
        response = await transcribe_route(
            TranscribeRequest(audio_b64=base64.b64encode(b"audio").decode()), service
        )
    finally:
        register_test_provider("groq_whisper", None)
    assert response.model_dump() == {
        "text": "hello", "language": "en", "duration_ms": 25,
        "provider": "groq_whisper", "cost_usd": 0.0,
    }
