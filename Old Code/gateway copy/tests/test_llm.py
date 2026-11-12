from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from gateway.llm.cache import SemanticCache
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
    async def stream(self, **kwargs: Any):
        yield b"ok"
    async def embed(self, text: str, *, model: str | None = None, task_type: str = "retrieval_document") -> list[float]: return [1.0, 0.0]


def budget_files(tmp_path: Path, *, limit: float | None = None) -> tuple[Path, Path]:
    policies = "[]" if limit is None else f"\n  - principal: 'session:*'\n    limit_usd: {limit}\n    period: lifetime"
    path = tmp_path / "budgets.yaml"
    path.write_text(f"version: 1\ndefaults:\n  enabled: true\n  period: day\nprojection: {{}}\npolicies: {policies}\nalerts: {{}}\n", encoding="utf-8")
    return path, tmp_path / "ledger.sqlite"


def service_for(tmp_path: Path, providers: list[FakeProvider]) -> tuple[LLMService, AuditSpy]:
    budget_path, database = budget_files(tmp_path)
    audit = AuditSpy()
    service = LLMService(registry=ProviderRegistry({x.name: x for x in providers}),
        profiles=ProfileRegistry({"chat": {"pin": {"provider": providers[-1].name, "model": providers[-1].model}}, "embedding": {"embed": {"provider": providers[-1].name, "model": providers[-1].model, "dim": 2}}}),
        pricing=PricingTable({"models": {}, "providers": {}, "unpriced_default": {"input": 0, "output": 0}}),
        budget=BudgetController(budget_path, database), meter=Meter(), audit=audit, cache=None)  # type: ignore[arg-type]
    return service, audit


def test_stage_nine_runs_after_retry_and_failover(tmp_path: Path) -> None:
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


def test_cache_miss_reuses_lookup_embedding_for_store(tmp_path: Path) -> None:
    calls = 0
    async def embed(_: str, _task_type: str) -> list[float]:
        nonlocal calls; calls += 1; return [1.0, 0.0]
    cache = SemanticCache(embed, tmp_path / "semantic-cache.sqlite")
    async def exercise() -> None:
        lookup = await cache.lookup("prompt", {"model": "x"}, opt_in=True)
        assert not lookup.hit
        cache.store("prompt", {"model": "x"}, {"text": "answer"}, lookup.embedding)
    asyncio.run(exercise())
    assert calls == 1


def test_semantic_cache_persists_across_instances_and_scopes_tenants(tmp_path: Path) -> None:
    async def embed(_: str, _task_type: str) -> list[float]:
        return [1.0, 0.0]

    database = tmp_path / "semantic-cache.sqlite"
    first = SemanticCache(embed, database)

    async def seed() -> None:
        lookup = await first.lookup(
            "first wording", {"model": "x"}, principal={"tenant": "one"}, opt_in=True,
        )
        first.store(
            "first wording", {"model": "x"}, {"text": "saved"}, lookup.embedding,
            principal={"tenant": "one"},
        )

    asyncio.run(seed())
    restarted = SemanticCache(embed, database)

    async def verify() -> None:
        hit = await restarted.lookup(
            "similar wording", {"model": "x"}, principal={"tenant": "one"}, opt_in=True,
        )
        assert hit.hit and hit.response == {"text": "saved"}
        other_tenant = await restarted.lookup(
            "similar wording", {"model": "x"}, principal={"tenant": "two"}, opt_in=True,
        )
        assert not other_tenant.hit

    asyncio.run(verify())


def test_semantic_cache_database_failure_does_not_serve_uncached(tmp_path: Path) -> None:
    async def embed(_: str, _task_type: str) -> list[float]:
        return [1.0, 0.0]

    cache = SemanticCache(embed, tmp_path / "semantic-cache.sqlite")
    cache.database.path = tmp_path  # SQLite cannot open a directory as a database.
    with pytest.raises(Exception):
        asyncio.run(cache.lookup("prompt", {"model": "x"}, opt_in=True))


def test_profile_resolution_is_an_exact_pin() -> None:
    profiles = ProfileRegistry({"chat": {"p": {"provider": "one", "model": "model-1"}}, "embedding": {"e": {"provider": "two", "model": "model-2", "dim": 3}}})
    assert profiles.resolve("chat", "p") == {"provider": "one", "model": "model-1"}
