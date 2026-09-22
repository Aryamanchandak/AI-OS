"""Request/response STT and TTS compatibility routes."""

from __future__ import annotations

import base64
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gateway.app.dependencies import get_channel_service
from gateway.app.router_registry import RouterRegistration
from gateway.channels.service import ChannelService
from gateway.voice.stt import STTError, transcribe
from gateway.voice.stt.router import PREFER_TO_PROVIDER as STT_PROVIDERS
from gateway.voice.tts import TTSError, synthesize
from gateway.voice.tts.router import PREFER_TO_PROVIDER as TTS_PROVIDERS

router = APIRouter()


class TranscribeRequest(BaseModel):
    audio_b64: str
    mime: str = "audio/wav"
    agent: str | None = None
    prefer: Literal["default", "local", "streaming"] = "default"


class TranscribeResponse(BaseModel):
    text: str
    language: str
    duration_ms: int
    provider: str
    cost_usd: float = Field(default=0.0)


class SpeakRequest(BaseModel):
    text: str
    voice_id: str | None = None
    agent: str | None = None
    prefer: Literal["default", "quality", "streaming", "realtime", "fallback"] = "default"


class SpeakResponse(BaseModel):
    audio_b64: str
    mime: str
    sample_rate: int
    provider: str
    cost_usd: float = 0.0


@router.post("/v1/transcribe", response_model=TranscribeResponse)
async def transcribe_route(
    request: TranscribeRequest,
    channels: Annotated[ChannelService, Depends(get_channel_service)],
) -> TranscribeResponse:
    provider = STT_PROVIDERS[request.prefer]
    if not channels.voice_enabled("stt", provider):
        raise HTTPException(503, f"STT provider '{provider}' is disabled")
    try:
        audio = base64.b64decode(request.audio_b64, validate=True)
    except Exception as exc:
        raise HTTPException(400, f"audio_b64 is not valid base64: {exc}") from exc
    try:
        result = await transcribe(audio, request.mime, prefer=request.prefer)
    except STTError as exc:
        if request.prefer == "streaming":
            raise HTTPException(400, str(exc)) from exc
        raise HTTPException(exc.status or 502, str(exc)) from exc
    return TranscribeResponse(**result.__dict__)


@router.post("/v1/speak", response_model=SpeakResponse)
async def speak_route(
    request: SpeakRequest,
    channels: Annotated[ChannelService, Depends(get_channel_service)],
) -> SpeakResponse:
    provider = TTS_PROVIDERS[request.prefer]
    if not channels.voice_enabled("tts", provider):
        raise HTTPException(503, f"TTS provider '{provider}' is disabled")
    try:
        result = await synthesize(request.text, voice_id=request.voice_id, prefer=request.prefer)
    except TTSError as exc:
        raise HTTPException(exc.status or 502, str(exc)) from exc
    return SpeakResponse(**result.__dict__)


def registration() -> RouterRegistration:
    return RouterRegistration(router=router, prefix="", tags=("voice",))
