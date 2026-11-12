from fastapi import HTTPException

from gateway.llm.orchestration.context import PipelineContext
from gateway.llm.providers.registry import ProviderRegistry


class RoutingStage:
    def __init__(self, registry: ProviderRegistry) -> None: self.registry = registry
    async def run(self, context: PipelineContext) -> None:
        if context.output is not None: return
        context.candidates = self.registry.candidates(context.request.provider)
        if not context.candidates:
            if context.request.profile:
                raise HTTPException(503, f"chat profile '{context.request.profile}' requires unavailable provider '{context.request.provider}'")
            if context.request.provider: raise HTTPException(400, f"unknown provider '{context.request.provider}'. Try one of: {list(self.registry.providers)}")
            raise HTTPException(503, "no LLM providers configured")
