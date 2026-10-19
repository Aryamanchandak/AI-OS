from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


from gateway.llm.economics import BudgetController, Meter, Principal, PricingTable
from gateway.llm.models import ChatRequest
from gateway.llm.profiles import ProfileRegistry
from gateway.llm.providers.base import ProviderCapabilities, ProviderError, ProviderResult, ProviderUsage
from gateway.llm.providers.registry import ProviderRegistry
from gateway.llm.service import LLMService


class AuditSpy:
    def __init__(self) -> None: self.events: list[dict[str, Any]] = []
    def append(self, **event: Any) -> int: self.events.append(event); return len(self.events)


class FakeProvider:
    capabilities = ProviderCapabilities()
    def __init__(self, name: str, *, fail: bool = False) -> None: self.name = name; self.model = f"{name}-model"; self.fail = fail; self.calls = 0
    async def chat(self, **kwargs: Any) -> ProviderResult:
        self.calls += 1
        if self.fail: raise ProviderError("temporary", status=503, retryable=True)
        return ProviderResult(provider=self.name, model=self.model, text="ok", usage=ProviderUsage(10, 2))
    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]: return [1.0, 0.0]


def budget_files(tmp_path: Path, *, limit: float | None = None) -> tuple[Path, Path]:
    policies = "[]" if limit is None else f"\n  - principal: 'session:*'\n    limit_usd: {limit}\n    period: lifetime"
    path = tmp_path / "budgets.yaml"
    path.write_text(f"version: 1\ndefaults:\n  enabled: true\n  period: day\npolicies: {policies}\n", encoding="utf-8")
    return path, tmp_path / "ledger.sqlite"


def service_for(tmp_path: Path, providers: list[FakeProvider]) -> tuple[LLMService, AuditSpy]:
    budget_path, database = budget_files(tmp_path)
    audit = AuditSpy()
    service = LLMService(registry=ProviderRegistry({x.name: x for x in providers}),
        profiles=ProfileRegistry({"chat": {"pin": {"provider": providers[-1].name, "model": providers[-1].model}}, "embedding": {"embed": {"provider": providers[-1].name, "model": providers[-1].model, "dim": 2}}}),
        pricing=PricingTable({"models": {}, "providers": {}, "unpriced_default": {"input": 0, "output": 0}}),
        budget=BudgetController(budget_path, database), meter=Meter(), audit=audit)  # type: ignore[arg-type]
    return service, audit


def test_finalization_runs_after_retry_and_failover(tmp_path: Path) -> None:
    failing, working = FakeProvider("failing", fail=True), FakeProvider("working")
    service, audit = service_for(tmp_path, [failing, working])
    result = asyncio.run(service.chat(ChatRequest(prompt="hello")))
    assert result["provider"] == "working"
    assert failing.calls == 2
    assert len(audit.events) == 1
    assert len(audit.events[0]["result"]["attempted"]) == 2


def test_atomic_budget_reservations_never_admit_over_ceiling(tmp_path: Path) -> None:
    path, database = budget_files(tmp_path, limit=0.05)
    controller = BudgetController(path, database)
    principal = Principal(session="run")
    with ThreadPoolExecutor(max_workers=20) as executor:
        admissions = list(executor.map(lambda _: controller.admit(principal, 0.01), range(20)))
    assert sum(item.allowed for item in admissions) == 5
    status = controller.status_for("session", "run")
    assert status is not None
    assert round(status.reserved_usd, 8) == 0.05


def test_profile_resolution_is_an_exact_pin() -> None:
    profiles = ProfileRegistry({"chat": {"p": {"provider": "one", "model": "model-1"}}, "embedding": {"e": {"provider": "two", "model": "model-2", "dim": 3}}})
    assert profiles.resolve("chat", "p") == {"provider": "one", "model": "model-1"}


def test_repeated_prompts_call_the_provider_each_time(tmp_path: Path) -> None:
    provider = FakeProvider('solo')
    service, audit = service_for(tmp_path, [provider])

    async def exercise() -> None:
        for _ in range(2):
            result = await service.chat(ChatRequest(prompt='same question'))
            assert result['text'] == 'ok'
            assert 'cache' not in result

    asyncio.run(exercise())
    assert provider.calls == len(audit.events) == 2


def test_runtime_budget_overrides_survive_restart_and_enforce_both_dimensions(tmp_path: Path) -> None:
    path, database = budget_files(tmp_path)
    first = BudgetController(path, database)
    first.set_limit('agent:reader', .1, 'lifetime')
    first.set_limit('session:*', .05, 'lifetime')
    restarted = BudgetController(path, database)
    principal = Principal(agent='reader', session='run-1')
    admission = restarted.admit(principal, .03)
    assert admission.allowed and len(admission.checked) == 2
    restarted.reconcile(admission.reservation_id, .03)
    refusal = restarted.admit(principal, .03)
    assert not refusal.allowed
    assert refusal.breached.dimension == 'session'
    assert restarted.status_for('agent', 'reader').spent_usd == .03
    assert restarted.status_for('session', 'run-1').spent_usd == .03


def test_old_runtime_budget_dimensions_are_not_loaded(tmp_path: Path) -> None:
    import sqlite3

    path, database = budget_files(tmp_path)
    controller = BudgetController(path, database)
    with sqlite3.connect(database) as connection:
        connection.execute('INSERT INTO llm_budget_limits VALUES(?,?,?,?,?,?,?)',
                           ('tenant:*', 'tenant', '*', 0, 'lifetime', 1, 0))
    controller.set_limit('agent:reader', 1)
    assert [policy.principal for policy in controller.policies()] == ['agent:reader']


def test_audit_attribution_uses_agent_and_session(tmp_path: Path) -> None:
    service, audit = service_for(tmp_path, [FakeProvider('solo')])
    asyncio.run(service.chat(ChatRequest(prompt='hello', agent='reader', session='run-1')))
    event = audit.events[0]
    assert event['channel_user_id'] == 'reader'
    assert event['session_id'] == 'run-1'
    assert event['result']['principal'] == {'agent': 'reader', 'session': 'run-1'}
