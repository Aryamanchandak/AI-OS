from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from gateway.ledger import CallLedger
from gateway.llm.economics import BudgetController, Principal, PricingTable
from gateway.llm.models import ChatRequest, ChatResponse, EmbedRequest, EmbedResponse, ToolCall
from gateway.llm.profiles import ProfileRegistry
from gateway.llm.providers.base import ProviderCapabilities, ProviderError, ProviderResult, ProviderUsage
from gateway.llm.providers.registry import ProviderRegistry
from gateway.llm.service import LLMService


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


def service_for(tmp_path: Path, providers: list[FakeProvider], *, price: float = 0) -> tuple[LLMService, CallLedger]:
    budget_path, database = budget_files(tmp_path)
    ledger = CallLedger(database)
    service = LLMService(registry=ProviderRegistry({x.name: x for x in providers}),  # type: ignore[dict-item]
        profiles=ProfileRegistry({"chat": {"pin": {"provider": providers[-1].name, "model": providers[-1].model}}, "embedding": {"embed": {"provider": providers[-1].name, "model": providers[-1].model, "dim": 2}}}),
        pricing=PricingTable({"models": {}, "providers": {}, "unpriced_default": {"input": price, "output": price}}),
        budget=BudgetController(budget_path, database), ledger=ledger)
    return service, ledger


def test_finalization_runs_after_retry_and_failover(tmp_path: Path) -> None:
    failing, working = FakeProvider("failing", fail=True), FakeProvider("working")
    service, ledger = service_for(tmp_path, [failing, working])
    result = asyncio.run(service.chat(ChatRequest(prompt="hello")))
    assert result["provider"] == "working"
    assert failing.calls == 2
    rows = ledger.recent()
    assert len(rows) == 1
    assert len(rows[0]["attempted"]) == 2


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
    service, ledger = service_for(tmp_path, [provider])

    async def exercise() -> None:
        for _ in range(2):
            result = await service.chat(ChatRequest(prompt='same question'))
            assert result['text'] == 'ok'
            assert 'cache' not in result

    asyncio.run(exercise())
    assert provider.calls == len(ledger.recent()) == 2


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


def test_chat_call_writes_one_complete_ledger_row(tmp_path: Path) -> None:
    service, ledger = service_for(tmp_path, [FakeProvider('solo')], price=1)
    asyncio.run(service.chat(ChatRequest(prompt='hello', agent='reader', session='run-1', profile='pin')))
    [row] = ledger.recent()
    assert {key: row[key] for key in ('kind', 'provider', 'model', 'input_tokens', 'output_tokens', 'agent', 'session', 'profile', 'status')} == {
        'kind': 'chat', 'provider': 'solo', 'model': 'solo-model', 'input_tokens': 10, 'output_tokens': 2,
        'agent': 'reader', 'session': 'run-1', 'profile': 'pin', 'status': 'ok'}
    assert row['usd'] == pytest.approx(12 / 1_000_000)


def embedder(name: str) -> FakeProvider:
    from dataclasses import replace

    provider = FakeProvider(name)
    provider.capabilities = replace(provider.capabilities, embeddings=True)
    return provider


def test_embed_call_writes_one_ledger_row(tmp_path: Path) -> None:
    service, ledger = service_for(tmp_path, [embedder('solo')])
    asyncio.run(service.embed(EmbedRequest(text='hello world', profile='embed')))
    [row] = ledger.recent()
    assert (row['kind'], row['provider'], row['model'], row['profile'], row['status']) == ('embed', 'solo', 'solo-model', 'embed', 'ok')


def test_ledger_has_no_update_or_delete(tmp_path: Path) -> None:
    ledger = CallLedger(tmp_path / 'gateway.sqlite')
    assert not hasattr(ledger, 'update') and not hasattr(ledger, 'delete')


@pytest.mark.parametrize('call', ['chat', 'embed'])
def test_failed_ledger_write_fails_the_call(tmp_path: Path, call: str) -> None:
    service, ledger = service_for(tmp_path, [embedder('solo')])
    ledger.database.path = tmp_path  # a directory cannot be opened as SQLite
    request = ChatRequest(prompt='hello') if call == 'chat' else EmbedRequest(text='hello', profile='embed')
    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(getattr(service, call)(request))


class ToolCallingProvider(FakeProvider):
    async def chat(self, **kwargs: Any) -> ProviderResult:
        return ProviderResult(provider=self.name, model=self.model, stop_reason='tool_use', usage=ProviderUsage(10, 2),
                              tool_calls=[{'id': 'call-1', 'name': 'lookup', 'arguments': {'q': 'x'}}])


@pytest.mark.parametrize('provider', [FakeProvider('solo'), ToolCallingProvider('solo')])
def test_chat_reply_matches_the_response_model(tmp_path: Path, provider: FakeProvider) -> None:
    service, _ = service_for(tmp_path, [provider])
    reply = ChatResponse.model_validate(asyncio.run(service.chat(ChatRequest(prompt='hello'))))
    assert all(isinstance(call, ToolCall) for call in reply.tool_calls)


def test_embed_reply_matches_the_response_model(tmp_path: Path) -> None:
    service, _ = service_for(tmp_path, [embedder('solo')])
    reply = EmbedResponse.model_validate(asyncio.run(service.embed(EmbedRequest(text='hello', profile='embed'))))
    assert reply.dim == len(reply.embedding) == 2
