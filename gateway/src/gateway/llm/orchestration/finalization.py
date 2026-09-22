import asyncio
import time

from gateway.audit import AuditStore
from gateway.llm.economics.budget import BudgetController
from gateway.llm.economics.meter import Meter
from gateway.llm.economics.pricing import PricingTable
from gateway.llm.orchestration.context import PipelineContext


class FinalizationStage:
    def __init__(self, meter: Meter, audit: AuditStore, budget: BudgetController, pricing: PricingTable) -> None:
        self.meter, self.audit, self.budget, self.pricing = meter, audit, budget, pricing

    async def run(self, context: PipelineContext) -> None:
        if context.finalized: return
        context.finalized = True; result = context.result; provider = result.provider if result else (context.provider.name if context.provider else context.request.provider or "(none)"); model = result.model if result else context.request.model or (context.provider.model if context.provider else "(none)")
        cost: dict[str, object] = self.pricing.cost(provider, model, result.usage, batch=context.request.batch) if result else {"total_usd": 0.0, "price_source": "no-provider-result"}
        context.cost = cost
        total_raw = cost.get("total_usd", 0.0)
        total_usd = float(total_raw) if isinstance(total_raw, (int, float, str)) else 0.0
        await asyncio.to_thread(self.budget.reconcile, context.admission.reservation_id if context.admission else None, total_usd, count=result is not None)
        record = {"provider": provider, "model": model, "principal": context.principal.present(), "input_tokens": result.usage.input_tokens if result else 0, "output_tokens": result.usage.output_tokens if result else 0, "cost_usd": total_usd, "latency_ms": int((time.monotonic() - context.started) * 1000), "status": "error" if context.error else "ok", "error": str(context.error)[:500] if context.error else None, "attempted": list(context.attempts), "retries": context.retries, "profile": context.request.profile, "cache_hit": context.cache_hit}
        self.meter.record(**record)
        await asyncio.to_thread(self.audit.append, channel="llm", channel_user_id=context.request.user or context.request.agent or "anonymous", trust_level="internal", event_type="llm.call", session_id=context.request.session, params={"provider": context.request.provider, "model": context.request.model, "profile": context.request.profile}, result=record)
