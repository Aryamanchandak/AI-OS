"""The model-call service: one chat path and one embedding path.

A chat call runs these steps in order, each in its own trace span:

    validate -> resolve_profile -> normalize -> route -> reserve_budget
    -> call_provider -> structured_output -> finalize

`finalize` always runs, on success, error or cancellation. It settles the
budget reservation and writes the one ledger row for the call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Any, TypeVar

from fastapi import HTTPException
from jsonschema import Draft202012Validator, ValidationError
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_exponential

from gateway.budget import Admission, BudgetController, Principal, period_start
from gateway.config import load_mapping
from gateway.content import content_has_image
from gateway.ledger import CallLedger
from gateway.models import ChatRequest, EmbedRequest
from gateway.pricing import PricingTable
from gateway.profiles import ProfileError, ProfileRegistry
from gateway.providers import Provider, ProviderError, ProviderRegistry, ProviderResult, build_provider_registry
from gateway.telemetry import stage_span

T = TypeVar("T")

MAX_SCHEMA_DEPTH = 40
MAX_SCHEMA_NODES = 5000


@dataclass(slots=True)
class _ChatCall:
    """Everything one chat call accumulates, so `finalize` can account for it."""

    request: ChatRequest
    started: float
    principal: Principal
    messages: list[dict[str, Any]] = field(default_factory=list)
    estimated_input_tokens: int = 0
    candidates: list[Provider] = field(default_factory=list)
    provider: Provider | None = None
    result: ProviderResult | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    retries: int = 0
    admission: Admission | None = None
    cost: dict[str, Any] | None = None
    error: BaseException | None = None


class LLMService:
    def __init__(self, *, registry: ProviderRegistry, profiles: ProfileRegistry, pricing: PricingTable,
                 budget: BudgetController, ledger: CallLedger,
                 max_retries: int = 0, max_concurrency: int = 32) -> None:
        self.registry = registry
        self.profiles = profiles
        self.pricing = pricing
        self.budget = budget
        self.ledger = ledger
        self.max_retries = max_retries
        self.tracer: Any = None
        self.set_max_concurrency(max_concurrency)

    @classmethod
    def build(cls, *, config_dir: Path, ledger: CallLedger) -> "LLMService":
        limits = load_mapping(config_dir / "providers.yaml")
        return cls(
            registry=build_provider_registry(config_dir=config_dir),
            profiles=ProfileRegistry.from_yaml(config_dir / "profiles.yaml"),
            pricing=PricingTable.from_yaml(config_dir / "pricing.yaml"),
            budget=BudgetController(config_dir / "budgets.yaml", ledger.database.path),
            ledger=ledger,
            max_retries=int(limits["max_retries"]),
            max_concurrency=int(limits["max_concurrency"]),
        )

    def set_max_concurrency(self, limit: int) -> None:
        """Chat and embeddings share this one cap on calls in flight."""
        self._semaphore = asyncio.Semaphore(limit)

    # --- chat --------------------------------------------------------------

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        call = _ChatCall(request=request, started=time.monotonic(), principal=Principal.from_request(request))
        steps: tuple[tuple[str, Callable[[_ChatCall], Awaitable[None]]], ...] = (
            ("validate", self._validate),
            ("resolve_profile", self._resolve_profile),
            ("normalize", self._normalize),
            ("route", self._route),
            ("reserve_budget", self._reserve_budget),
            ("call_provider", self._call_provider),
            ("structured_output", self._structured_output),
        )
        try:
            for name, step in steps:
                with stage_span(self.tracer, f"llm.{name}"):
                    await step(call)
        except BaseException as exc:
            call.error = exc
            raise
        finally:
            with stage_span(self.tracer, "llm.finalize"):
                await self._finalize(call)

        result = call.result
        assert result is not None
        return {
            "provider": result.provider,
            "model": result.model,
            "profile": request.profile,
            "text": result.text,
            "tool_calls": result.tool_calls,
            "stop_reason": result.stop_reason,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cache_creation_input_tokens": result.usage.cache_creation_input_tokens,
            "cache_read_input_tokens": result.usage.cache_read_input_tokens,
            "latency_ms": int((time.monotonic() - call.started) * 1000),
            "tool_call_dialect": result.tool_call_dialect,
            "reasoning_applied": result.reasoning_applied,
            "parsed": result.raw.get("parsed"),
            "attempted": call.attempts,
            "retries": call.retries,
            "trace": None,
            "cost": call.cost,
            "budget": call.admission.as_dict() if call.admission else None,
        }

    async def _validate(self, call: _ChatCall) -> None:
        request = call.request
        if request.profile and (request.provider or request.model):
            raise HTTPException(400, "chat profile is mutually exclusive with provider/model")
        if request.messages is None and request.prompt is None:
            raise HTTPException(400, "either messages or prompt is required")
        if request.max_tokens <= 0:
            raise HTTPException(400, "max_tokens must be positive")
        if request.response_format and request.response_format.schema_:
            _check_schema_size(request.response_format.schema_)

    async def _resolve_profile(self, call: _ChatCall) -> None:
        """A profile pins the provider and model; the request is updated in place."""
        request = call.request
        if not request.profile:
            return
        try:
            spec = self.profiles.resolve("chat", request.profile)
        except ProfileError as exc:
            raise HTTPException(400, str(exc)) from exc
        request.provider = spec["provider"]
        request.model = spec["model"]

    async def _normalize(self, call: _ChatCall) -> None:
        """Build the message list, reject image links, and estimate input tokens."""
        request = call.request
        call.messages = list(request.messages or [{"role": "user", "content": request.prompt or ""}])
        for message in call.messages:
            _reject_image_links(message.get("content"))
        prompt_chars = sum(len(_plain_text(message.get("content", ""))) for message in call.messages)
        system_chars = len(str(request.system or ""))
        call.estimated_input_tokens = max(1, (prompt_chars + system_chars + 3) // 4)

    async def _route(self, call: _ChatCall) -> None:
        """Pick the providers to try: the named one, or every provider in order."""
        request = call.request
        call.candidates = self.registry.candidates(request.provider)
        if not call.candidates:
            if request.profile:
                raise HTTPException(
                    503, f"chat profile '{request.profile}' requires unavailable provider '{request.provider}'")
            if request.provider:
                raise HTTPException(
                    400, f"unknown provider '{request.provider}'. Try one of: {list(self.registry.providers)}")
            raise HTTPException(503, "no LLM providers configured")
        if any(content_has_image(message.get("content")) for message in call.messages):
            call.candidates = [provider for provider in call.candidates if provider.capabilities.vision]
            if not call.candidates:
                raise HTTPException(
                    400, "Images require a vision-capable model; choose a vision-capable provider or profile")

    async def _reserve_budget(self, call: _ChatCall) -> None:
        """Reserve the cost of the dearest candidate, so failover is covered too."""
        request = call.request
        projection = max(
            self.pricing.project(provider.name, request.model or provider.model,
                                 call.estimated_input_tokens, request.max_tokens)
            for provider in call.candidates
        )
        call.admission = await asyncio.to_thread(self.budget.admit, call.principal, projection)
        if not call.admission.allowed:
            raise HTTPException(402, call.admission.envelope())

    async def _call_provider(self, call: _ChatCall) -> None:
        request = call.request
        last: BaseException | None = None

        def count_retry(_: RetryCallState) -> None:
            call.retries += 1

        for provider in call.candidates:
            call.provider = provider

            async def ask(provider: Provider = provider) -> ProviderResult:
                return await provider.chat(
                    messages=call.messages, system=request.system, model=request.model,
                    max_tokens=request.max_tokens, temperature=request.temperature,
                    tools=request.tools, tool_choice=request.tool_choice,
                    response_format=request.response_format, reasoning=request.reasoning,
                    cache_system=bool(request.cache_system),
                )

            try:
                result = await self._with_retries(provider, ask, call.attempts, before_sleep=count_retry)
            except HTTPException:
                raise
            except Exception as exc:
                last = exc
                if request.provider or _permanent_client_error(exc):
                    break
                continue
            call.result = result
            if request.profile and result.model != request.model:
                # A pin mismatch is a configuration fault, not a transient provider fault:
                # report it as itself rather than as "all providers unavailable".
                raise HTTPException(
                    500, f"chat profile '{request.profile}' expected model '{request.model}' "
                         f"but provider '{provider.name}' returned '{result.model}'")
            return
        raise _provider_failure(last, request.provider, call.attempts)

    async def _structured_output(self, call: _ChatCall) -> None:
        """When a response format was asked for, the reply must be JSON that fits the schema."""
        result, response_format = call.result, call.request.response_format
        if result is None or response_format is None or result.tool_calls:
            return
        try:
            parsed = json.loads(result.text)
            if response_format.schema_ is not None:
                Draft202012Validator(response_format.schema_).validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(502, f"provider returned invalid structured output: {exc}") from exc
        result.raw["parsed"] = parsed

    async def _finalize(self, call: _ChatCall) -> None:
        request, result = call.request, call.result
        if result:
            provider, model = result.provider, result.model
            cost = self.pricing.cost(provider, model, result.usage)
        else:
            provider = call.provider.name if call.provider else request.provider or "(none)"
            model = request.model or (call.provider.model if call.provider else "(none)")
            cost = {"total_usd": 0.0, "price_source": "no-provider-result"}
        call.cost = cost
        total = cost.get("total_usd", 0.0)
        total_usd = float(total) if isinstance(total, (int, float, str)) else 0.0
        refused = call.admission is not None and not call.admission.allowed

        await asyncio.to_thread(
            self.budget.reconcile,
            call.admission.reservation_id if call.admission else None,
            total_usd,
            count=result is not None,
        )
        # Fail closed: if this write raises, the call fails rather than leaving unlogged spend.
        await asyncio.to_thread(
            self.ledger.append,
            kind="chat", provider=provider, model=model, **call.principal.present(),
            input_tokens=result.usage.input_tokens if result else 0,
            output_tokens=result.usage.output_tokens if result else 0,
            cache_read_tokens=result.usage.cache_read_input_tokens if result else 0,
            cache_create_tokens=result.usage.cache_creation_input_tokens if result else 0,
            usd=total_usd, price_source=str(cost.get("price_source")),
            latency_ms=int((time.monotonic() - call.started) * 1000),
            status="refused" if refused else "error" if call.error else "ok",
            error=str(call.error)[:500] if call.error else None,
            attempted=list(call.attempts), retries=call.retries, profile=request.profile,
        )

    # --- embeddings --------------------------------------------------------

    async def embed(self, request: EmbedRequest) -> dict[str, Any]:
        started = time.monotonic()
        attempts: list[dict[str, Any]] = []
        selected, model, expected_dim = request.provider, request.model, None
        if request.profile:
            if request.provider or request.model:
                raise HTTPException(400, "embedding profile is mutually exclusive with provider/model")
            try:
                spec = self.profiles.resolve("embedding", request.profile)
            except ProfileError as exc:
                raise HTTPException(400, str(exc)) from exc
            selected, model, expected_dim = spec["provider"], spec["model"], spec["dim"]
        candidates = self.registry.candidates(selected)
        if not candidates:
            raise HTTPException(503, f"no embedding provider configured for '{selected or 'any'}'")

        result: dict[str, Any] | None = None
        error: BaseException | None = None
        try:
            for provider in candidates:
                if not provider.capabilities.embeddings:
                    continue

                async def embed_once(provider: Provider = provider) -> list[float]:
                    vector = await provider.embed(request.text, model=model, task_type=request.task_type)
                    if expected_dim is not None and len(vector) != expected_dim:
                        raise ProviderError(
                            f"embedding profile '{request.profile}' expected dimension {expected_dim} "
                            f"but provider '{provider.name}' returned {len(vector)}")
                    return vector

                try:
                    vector = await self._with_retries(provider, embed_once, attempts)
                except HTTPException:
                    raise
                except Exception as exc:
                    error = exc
                    if selected or _permanent_client_error(exc):
                        break
                    continue
                result = {
                    "provider": provider.name, "model": model or provider.model,
                    "embedding": vector, "dim": len(vector),
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "attempted": attempts, "profile": request.profile,
                }
                return result
            raise _provider_failure(error, selected, attempts)
        except BaseException as exc:
            error = exc
            raise
        finally:
            await asyncio.to_thread(
                self.ledger.append,
                kind="embed",
                provider=result["provider"] if result else selected or "(any)",
                model=result["model"] if result else model or "(none)",
                input_tokens=max(1, len(request.text) // 4),
                latency_ms=int((time.monotonic() - started) * 1000),
                status="ok" if result else "error",
                error=str(error)[:500] if error and not result else None,
                attempted=attempts, profile=request.profile,
            )

    # --- shared by chat and embeddings -------------------------------------

    async def _with_retries(self, provider: Provider, operation: Callable[[], Awaitable[T]],
                            attempts: list[dict[str, Any]], *,
                            before_sleep: Callable[[RetryCallState], None] = lambda _: None) -> T:
        """Run one provider call under the concurrency cap, retrying retryable provider errors."""
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self.max_retries + 1),
            wait=wait_exponential(multiplier=0.5, max=2),
            retry=retry_if_exception(lambda exc: isinstance(exc, ProviderError) and exc.retryable),
            before_sleep=before_sleep,
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                try:
                    async with self._semaphore:
                        return await operation()
                except HTTPException:
                    raise
                except Exception as exc:
                    attempts.append({"provider": provider.name, "reason": str(exc)[:120]})
                    raise
        raise AssertionError("retry loop ended without a result or exception")

    # --- read-only views for the diagnostic routes --------------------------

    def providers(self) -> dict[str, Any]:
        return {
            "order": self.registry.order,
            "providers": list(self.registry.providers),
            "models": {name: provider.model for name, provider in self.registry.providers.items()},
            "chat_profiles": {
                name: {**spec, "available": spec["provider"] in self.registry.providers}
                for name, spec in self.profiles.all("chat").items()
            },
        }

    def capabilities(self) -> dict[str, Any]:
        return self.registry.diagnostics()

    def today(self) -> dict[str, Any]:
        return self.ledger.by_provider(since=period_start("day"))

    def status(self) -> dict[str, Any]:
        return {"order": self.registry.order, "today": self.today()}


def _check_schema_size(value: object, *, depth: int = 0, counter: list[int] | None = None) -> None:
    count = counter if counter is not None else [0]
    count[0] += 1
    if depth > MAX_SCHEMA_DEPTH:
        raise HTTPException(400, f"response schema exceeds maximum depth {MAX_SCHEMA_DEPTH}")
    if count[0] > MAX_SCHEMA_NODES:
        raise HTTPException(400, f"response schema exceeds maximum node count {MAX_SCHEMA_NODES}")
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    for item in children:
        _check_schema_size(item, depth=depth + 1, counter=count)


def _reject_image_links(content: Any) -> None:
    """Images must arrive as base64 or a `data:` URL; the gateway never fetches a link."""
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "image_url":
            image = block.get("image_url")
            url = image.get("url") if isinstance(image, dict) else image
        elif kind in {"image", "input_image"}:
            source = block.get("source") or {}
            if isinstance(source, dict) and source.get("type") == "base64":
                continue
            url = block.get("url") or (source.get("url") if isinstance(source, dict) else None)
        else:
            continue
        if not isinstance(url, str) or not url.startswith("data:"):
            raise HTTPException(400, "Image links are not supported; send the image as a data: URL")


def _plain_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", "")) for block in content
            if isinstance(block, dict) and block.get("type") == "text")
    return str(content or "")


def _permanent_client_error(exc: BaseException | None) -> bool:
    return isinstance(exc, ProviderError) and 400 <= exc.status < 500 and not exc.retryable


def _provider_failure(exc: BaseException | None, selected: str | None,
                      attempts: list[dict[str, Any]]) -> HTTPException:
    """The caller's status when a provider was named or the error is permanent; otherwise 503."""
    status = exc.status if isinstance(exc, ProviderError) and (selected or _permanent_client_error(exc)) else 503
    return HTTPException(status, f"all providers unavailable. attempts: {attempts}. last_error: {exc}")
