import asyncio

from fastapi import HTTPException

from gateway.llm.economics.budget import BudgetController
from gateway.llm.economics.pricing import PricingTable
from gateway.llm.orchestration.context import PipelineContext


class BudgetReservationStage:
    def __init__(self, controller: BudgetController, pricing: PricingTable) -> None: self.controller, self.pricing = controller, pricing
    async def run(self, context: PipelineContext) -> None:
        if context.output is not None: return
        request = context.request
        # Failover candidates are covered by the initial reservation too.
        projection = max(self.pricing.project(provider.name, request.model or provider.model, context.estimated_input_tokens, request.max_tokens, batch=request.batch) for provider in context.candidates)
        context.admission = await asyncio.to_thread(self.controller.admit, context.principal, projection)
        if not context.admission.allowed: raise HTTPException(402, context.admission.envelope())
