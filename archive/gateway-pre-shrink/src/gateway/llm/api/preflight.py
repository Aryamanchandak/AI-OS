"""Bounded chat and embedding probes through the normal LLM service."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import HTTPException

from gateway.llm import LLMService
from gateway.llm.models import ChatRequest, EmbedRequest, PreflightCheck, PreflightRequest, PreflightResponse
from gateway.platform.observability.redaction import safe_error

PREFLIGHT_TIMEOUT_S = 30.0


async def run_preflight(request: PreflightRequest, service: LLMService) -> PreflightResponse:
    async def check(kind: str) -> PreflightCheck:
        started = time.perf_counter()
        profile = request.chat_profile if kind == "chat" else request.embedding_profile
        try:
            async with asyncio.timeout(PREFLIGHT_TIMEOUT_S):
                result: dict[str, Any]
                if kind == "chat":
                    result = await service.chat(ChatRequest(
                        prompt="Reply with OK.", profile=profile,
                        provider=request.chat_provider, model=request.chat_model,
                        max_tokens=8, temperature=0, reasoning="off",
                        semantic_cache=False, escalate=False,
                    ))
                else:
                    result = await service.embed(EmbedRequest(text="preflight check", profile=profile))
            return PreflightCheck(
                ok=True, profile=result.get("profile"), provider=result.get("provider"),
                model=result.get("model"), dim=result.get("dim"),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            status = exc.status_code if isinstance(exc, HTTPException) else getattr(exc, "status", None)
            if isinstance(exc, TimeoutError):
                status = 504
            return PreflightCheck(
                ok=False, profile=profile, latency_ms=int((time.perf_counter() - started) * 1000),
                status_code=status,
                error=safe_error(exc.detail if isinstance(exc, HTTPException) else exc) or "probe timed out",
            )

    chat, embedding = await asyncio.gather(check("chat"), check("embedding"))
    return PreflightResponse(ok=chat.ok and embedding.ok, chat=chat, embedding=embedding)
