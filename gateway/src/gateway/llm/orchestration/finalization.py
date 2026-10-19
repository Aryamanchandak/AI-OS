import asyncio
import time

from gateway.ledger import CallLedger
from gateway.llm.economics.budget import BudgetController
from gateway.llm.economics.pricing import PricingTable
from gateway.llm.orchestration.context import PipelineContext


class FinalizationStage:
    def __init__(self, ledger: CallLedger, budget: BudgetController, pricing: PricingTable) -> None:
        self.ledger, self.budget, self.pricing = ledger, budget, pricing

    async def run(self, context: PipelineContext) -> None:
        if context.finalized: return
        context.finalized = True; result = context.result; provider = result.provider if result else (context.provider.name if context.provider else context.request.provider or "(none)"); model = result.model if result else context.request.model or (context.provider.model if context.provider else "(none)")
        cost: dict[str, object] = self.pricing.cost(provider, model, result.usage) if result else {"total_usd": 0.0, "price_source": "no-provider-result"}
        context.cost = cost
        total_raw = cost.get("total_usd", 0.0)
        total_usd = float(total_raw) if isinstance(total_raw, (int, float, str)) else 0.0
        await asyncio.to_thread(self.budget.reconcile, context.admission.reservation_id if context.admission else None, total_usd, count=result is not None)
        # Fail closed: if this write raises, the call fails rather than leaving unlogged spend.
        await asyncio.to_thread(self.ledger.append, kind="chat", provider=provider, model=model, **context.principal.present(),
            input_tokens=result.usage.input_tokens if result else 0, output_tokens=result.usage.output_tokens if result else 0,
            cache_read_tokens=result.usage.cache_read_input_tokens if result else 0, cache_create_tokens=result.usage.cache_creation_input_tokens if result else 0,
            usd=total_usd, price_source=str(cost.get("price_source")), latency_ms=int((time.monotonic() - context.started) * 1000),
            status="error" if context.error else "ok", error=str(context.error)[:500] if context.error else None,
            attempted=list(context.attempts), retries=context.retries, profile=context.request.profile)
