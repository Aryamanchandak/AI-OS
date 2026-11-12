"""Ten-stage LLM pipeline; stage nine executes from the finally boundary."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from collections.abc import AsyncIterator
import time
from typing import Any

from gateway.llm.economics.meter import Principal
from gateway.llm.models import ChatRequest
from gateway.llm.orchestration.budget import BudgetReservationStage
from gateway.llm.orchestration.cache_lookup import CacheLookupStage
from gateway.llm.orchestration.cache_store import CacheStoreStage
from gateway.llm.orchestration.context import PipelineContext
from gateway.llm.orchestration.finalization import FinalizationStage
from gateway.llm.orchestration.normalization import NormalizationStage
from gateway.llm.orchestration.profile_resolution import ProfileResolutionStage
from gateway.llm.orchestration.provider_call import ProviderCallStage
from gateway.llm.orchestration.routing import RoutingStage
from gateway.llm.orchestration.streaming import (
    delta_frame, done_frame, error_frame, tool_call_delta_frame,
)
from gateway.llm.orchestration.structured_output import StructuredOutputStage
from gateway.llm.orchestration.validation import RequestValidationStage
from gateway.llm.providers.base import TOOL_CALL_DELTA, ProviderError, ProviderResult


class LLMPipeline:
    def __init__(self, *, validation: RequestValidationStage, profiles: ProfileResolutionStage,
                 normalization: NormalizationStage, cache_lookup: CacheLookupStage,
                 routing: RoutingStage, budget: BudgetReservationStage,
                 provider_call: ProviderCallStage, structured: StructuredOutputStage,
                 finalization: FinalizationStage, cache_store: CacheStoreStage) -> None:
        self.validation, self.profiles, self.normalization = validation, profiles, normalization
        self.cache_lookup, self.routing, self.budget = cache_lookup, routing, budget
        self.provider_call, self.structured = provider_call, structured
        self.finalization, self.cache_store = finalization, cache_store
        self.tracer: Any = None

    async def _run_stage(self, stage: Any, context: PipelineContext) -> None:
        boundary = (
            self.tracer.start_as_current_span(
                f"llm.{type(stage).__name__}", record_exception=False, set_status_on_exception=False,
            ) if self.tracer is not None else nullcontext()
        )
        with boundary as span:
            try:
                await stage.run(context)
            except BaseException:
                if span is not None:
                    from opentelemetry.trace import StatusCode
                    span.set_status(StatusCode.ERROR)
                raise

    async def run_stream(self, request: ChatRequest) -> dict[str, Any] | AsyncIterator[str]:
        """Stages 1–6 eagerly, then an SSE generator that owns stages 7 and 9.

        Stages 1–6 run before a single byte is committed, so a 400/402/503 from
        validation, budget or routing still reaches the caller as a normal JSON
        error response rather than as an error frame inside a 200.

        Stage 9 runs from the *generator's* `finally`, not this function's: a
        `StreamingResponse` returns the moment the generator is handed over, so
        finalizing here would meter the call before any provider work happened.
        Putting it in the generator also means a client disconnect — which
        arrives as `GeneratorExit` — still meters and still reconciles the
        budget reservation.

        Returns a **dict** rather than a generator on a semantic-cache hit: the
        legacy route returns the stored response body directly regardless of
        `stream` (`glc_v5/glc/routes/chat.py:691`), so a hit answers a streaming
        request with JSON, not with SSE frames. Routing and budget both early-
        return once the cache has filled `context.output`, which is why no
        provider candidate exists on that branch.
        """
        context = PipelineContext(request=request, started=time.monotonic(), principal=Principal.from_request(request))
        try:
            for stage in (self.validation, self.profiles, self.normalization,
                          self.cache_lookup, self.routing, self.budget):
                await self._run_stage(stage, context)
        except BaseException as exc:
            context.error = exc
            await self._run_stage(self.finalization, context)
            raise
        if context.output is not None:
            await self._run_stage(self.finalization, context)
            return await self._finish(context)
        return self._stream_frames(context)

    async def _finish(self, context: PipelineContext) -> dict[str, Any]:
        """Stage 10: attach economics to the response and store it in the cache."""
        assert context.output is not None
        context.output["cost"] = context.cost
        context.output["budget"] = context.admission.as_dict() if context.admission else None
        await self._run_stage(self.cache_store, context)
        return context.output

    async def _stream_frames(self, context: PipelineContext) -> AsyncIterator[str]:
        request = context.request
        provider = context.candidates[0]
        context.provider = provider
        sink: dict[str, Any] = {}
        expected = request.model if request.profile else None
        try:
            async for chunk in provider.stream(
                messages=context.messages, system=context.system, model=request.model,
                max_tokens=request.max_tokens, temperature=request.temperature,
                tools=request.tools, tool_choice=request.tool_choice,
                response_format=request.response_format, reasoning=request.reasoning,
                cache_system=bool(request.cache_system), result_sink=sink,
            ):
                if chunk.startswith(TOOL_CALL_DELTA):
                    yield tool_call_delta_frame(provider.name, chunk[len(TOOL_CALL_DELTA) + 1:])
                else:
                    yield delta_frame(provider.name, chunk)

            # The model the vendor actually echoed, when the provider could
            # confirm one mid-stream. A buffered provider always can; a genuinely
            # incremental one only does when its chunks carry the field.
            confirmed = sink.get("model")
            if isinstance(sink.get("result"), ProviderResult):
                context.result = sink["result"]
            model_used = confirmed or request.model or provider.model

            if expected and confirmed is not None and confirmed != expected:
                detail = (f"chat profile '{request.profile}' expected model '{expected}' "
                          f"but provider '{provider.name}' returned '{confirmed}'")
                context.error = ProviderError(detail, status=500)
                context.attempts.append({"provider": provider.name, "reason": detail[:120]})
                yield error_frame(detail)
                return  # no done frame after a pin mismatch — legacy's shape

            yield done_frame(provider.name, model_used, request.profile,
                             pin_unverified=bool(expected) and confirmed is None)
        except (GeneratorExit, asyncio.CancelledError) as exc:
            # The client went away or the request was cancelled. Nothing may be
            # yielded into a closing generator, so record and re-raise; the
            # `finally` below still meters the partial call.
            context.error = exc
            raise
        except BaseException as exc:
            context.error = exc
            yield error_frame(str(exc))
        finally:
            # Stage 9 is unconditional here too, disconnects included.
            await self._run_stage(self.finalization, context)

    async def run(self, request: ChatRequest) -> dict[str, Any]:
        context = PipelineContext(request=request, started=time.monotonic(), principal=Principal.from_request(request))
        try:
            for stage in (self.validation, self.profiles, self.normalization, self.cache_lookup,
                          self.routing, self.budget, self.provider_call, self.structured):
                await self._run_stage(stage, context)
            if context.output is None:
                result = context.result
                assert result is not None
                context.output = {
                    "provider": result.provider, "model": result.model, "profile": request.profile,
                    "text": result.text, "tool_calls": result.tool_calls, "stop_reason": result.stop_reason,
                    "input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens,
                    "cache_creation_input_tokens": result.usage.cache_creation_input_tokens,
                    "cache_read_input_tokens": result.usage.cache_read_input_tokens,
                    "latency_ms": int((time.monotonic() - context.started) * 1000),
                    "tool_call_dialect": result.tool_call_dialect, "reasoning_applied": result.reasoning_applied,
                    "parsed": result.raw.get("parsed"), "attempted": context.attempts, "router_decision": None,
                    "retries": context.retries, "cache": {"hit": False} if request.semantic_cache else None,
                    "trace": None,
                }
        except BaseException as exc:
            context.error = exc
            raise
        finally:
            # Stage 9 is unconditional: retry/failover/error paths cannot skip it.
            await self._run_stage(self.finalization, context)
        # Stage 10 reuses stage 4's embedding and performs response translation.
        return await self._finish(context)
