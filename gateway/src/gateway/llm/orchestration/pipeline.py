"""Chat pipeline with unconditional accounting at the finally boundary."""

from __future__ import annotations

import time
from typing import Any

from gateway.llm.economics.budget import Principal
from gateway.llm.models import ChatRequest
from gateway.llm.orchestration.budget import BudgetReservationStage
from gateway.llm.orchestration.context import PipelineContext
from gateway.llm.orchestration.finalization import FinalizationStage
from gateway.llm.orchestration.normalization import NormalizationStage
from gateway.llm.orchestration.profile_resolution import ProfileResolutionStage
from gateway.llm.orchestration.provider_call import ProviderCallStage
from gateway.llm.orchestration.routing import RoutingStage
from gateway.llm.orchestration.structured_output import StructuredOutputStage
from gateway.llm.orchestration.validation import RequestValidationStage
from gateway.telemetry import stage_span


class LLMPipeline:
    def __init__(self, *, validation: RequestValidationStage, profiles: ProfileResolutionStage,
                 normalization: NormalizationStage,
                 routing: RoutingStage, budget: BudgetReservationStage,
                 provider_call: ProviderCallStage, structured: StructuredOutputStage,
                 finalization: FinalizationStage) -> None:
        self.validation, self.profiles, self.normalization = validation, profiles, normalization
        self.routing, self.budget = routing, budget
        self.provider_call, self.structured = provider_call, structured
        self.finalization = finalization
        self.tracer: Any = None

    async def _run_stage(self, stage: Any, context: PipelineContext) -> None:
        with stage_span(self.tracer, f"llm.{type(stage).__name__}"):
            await stage.run(context)

    async def run(self, request: ChatRequest) -> dict[str, Any]:
        context = PipelineContext(request=request, started=time.monotonic(), principal=Principal.from_request(request))
        try:
            for stage in (self.validation, self.profiles, self.normalization,
                          self.routing, self.budget, self.provider_call, self.structured):
                await self._run_stage(stage, context)
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
                "parsed": result.raw.get("parsed"), "attempted": context.attempts,
                "retries": context.retries,
                "trace": None,
            }
        except BaseException as exc:
            context.error = exc
            raise
        finally:
            # Finalization is unconditional: retry/failover/error paths cannot skip it.
            await self._run_stage(self.finalization, context)
        # Attach cost and budget after finalization.
        assert context.output is not None
        context.output["cost"] = context.cost
        context.output["budget"] = context.admission.as_dict() if context.admission else None
        return context.output
