"""POST /v1/transcribe route — request validation and provider routing.

Ported from glc_v5/tests/test_transcribe_route.py (Plan 01 baseline fixture,
migration/baseline/contracts.md: "Transcription + speech"). The original used
an app-wide `app_client` fixture against a GLC app where voice providers were
always reachable; the Gateway route additionally gates on
`channels.voice_enabled("stt", provider)` per Plan 05 decision 5 (dormant by
default), so each case here builds a minimal ChannelService with the relevant
provider explicitly enabled, matching the pattern already established in
test_channels_voice_migration.py. Response codes and shapes are otherwise
unchanged from the original.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi import HTTPException

from gateway.audit import AuditStore
from gateway.channels.service import ChannelService
from gateway.security import Allowlist, PairingStore, RateLimiter
from gateway.voice.routes import TranscribeRequest, transcribe_route
from gateway.voice.stt.base import STTError, STTProvider, TranscribeResult
from gateway.voice.stt.router import register_test_provider


def _fake_provider(name: str, *, text: str = "hello", raise_: STTError | None = None) -> STTProvider:
    class Fake(STTProvider):
        async def transcribe(self, audio: bytes, mime: str) -> TranscribeResult:
            if raise_ is not None:
                raise raise_
            return TranscribeResult(text=text, language="en", duration_ms=10, provider=name, cost_usd=0.0)

    Fake.name = name
    return Fake()


@pytest.fixture(autouse=True)
def _clean_providers():
    yield
    for n in ("groq_whisper", "whisper_cpp", "gemini_live"):
        register_test_provider(n, None)


def _service(tmp_path: Path, *, enabled: dict[str, bool]) -> ChannelService:
    configuration = {
        "defaults": {}, "channels": {},
        "voice": {"stt": {name: {"enabled": on} for name, on in enabled.items()}, "tts": {}},
    }
    limiter = RateLimiter()
    limiter.configure(configuration)
    return ChannelService(
        configuration=configuration,
        pairings=PairingStore(tmp_path / "pairings.sqlite"),
        limiter=limiter,
        allowlist=Allowlist(configuration),
        audit=AuditStore(tmp_path / "audit.sqlite"),
        bridge=None,  # type: ignore[arg-type]
        services=None,  # type: ignore[arg-type]
    )


@pytest.mark.anyio
async def test_transcribe_streaming_returns_400(tmp_path: Path) -> None:
    service = _service(tmp_path, enabled={"gemini_live": True})
    body = {"audio_b64": base64.b64encode(b"\x00\x00").decode(), "mime": "audio/wav", "prefer": "streaming"}
    with pytest.raises(HTTPException) as excinfo:
        await transcribe_route(TranscribeRequest(**body), service)
    assert excinfo.value.status_code == 400


@pytest.mark.anyio
async def test_transcribe_bad_base64_returns_400(tmp_path: Path) -> None:
    service = _service(tmp_path, enabled={"groq_whisper": True})
    with pytest.raises(HTTPException) as excinfo:
        await transcribe_route(
            TranscribeRequest(audio_b64="!!!not-base64!!!", mime="audio/wav"), service
        )
    assert excinfo.value.status_code in (400, 502)


@pytest.mark.anyio
async def test_transcribe_default_calls_registered_provider(tmp_path: Path) -> None:
    service = _service(tmp_path, enabled={"groq_whisper": True})
    register_test_provider("groq_whisper", _fake_provider("groq_whisper"))
    body = {"audio_b64": base64.b64encode(b"\x00" * 100).decode(), "mime": "audio/wav", "prefer": "default"}
    response = await transcribe_route(TranscribeRequest(**body), service)
    assert response.text == "hello"
    assert response.provider == "groq_whisper"


@pytest.mark.anyio
async def test_transcribe_provider_error_becomes_502(tmp_path: Path) -> None:
    service = _service(tmp_path, enabled={"groq_whisper": True})
    register_test_provider(
        "groq_whisper",
        _fake_provider("groq_whisper", raise_=STTError("groq HTTP 500: upstream is down")),
    )
    body = {"audio_b64": base64.b64encode(b"\x00").decode(), "mime": "audio/wav", "prefer": "default"}
    with pytest.raises(HTTPException) as excinfo:
        await transcribe_route(TranscribeRequest(**body), service)
    assert excinfo.value.status_code == 502


@pytest.mark.anyio
async def test_transcribe_stub_returns_501(tmp_path: Path) -> None:
    """No real provider registered — the catalogue stub raises
    NotImplementedError, the dispatcher converts it to status=501."""
    service = _service(tmp_path, enabled={"groq_whisper": True})

    class Stub(STTProvider):
        name = "groq_whisper"

        async def transcribe(self, audio: bytes, mime: str) -> TranscribeResult:
            raise NotImplementedError("assignment stub")

    register_test_provider("groq_whisper", Stub())
    body = {"audio_b64": base64.b64encode(b"\x00").decode(), "mime": "audio/wav", "prefer": "default"}
    with pytest.raises(HTTPException) as excinfo:
        await transcribe_route(TranscribeRequest(**body), service)
    assert excinfo.value.status_code == 501
