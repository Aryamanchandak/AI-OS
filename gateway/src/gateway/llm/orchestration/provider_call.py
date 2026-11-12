import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import HTTPException
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_exponential

from gateway.llm.orchestration.context import PipelineContext
from gateway.llm.providers.base import Provider, ProviderError, ProviderResult

T = TypeVar("T")


def permanent_client_error(exc: BaseException | None) -> bool:
    return isinstance(exc, ProviderError) and 400 <= exc.status < 500 and not exc.retryable


def provider_failure(exc: BaseException | None, selected: str | None, attempts: list[dict[str, Any]]) -> HTTPException:
    status = exc.status if isinstance(exc, ProviderError) and (selected or permanent_client_error(exc)) else 503
    return HTTPException(status, f"all providers unavailable. attempts: {attempts}. last_error: {exc}")


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, ProviderError) and exc.retryable


class ProviderCallStage:
    def __init__(self, *, max_retries: int = 0, max_concurrency: int = 32) -> None:
        self.max_retries = max_retries; self._semaphore = asyncio.Semaphore(max_concurrency)

    async def call(self, provider: Provider, operation: Callable[[], Awaitable[T]],
                   attempts: list[dict[str, Any]], *,
                   before_sleep: Callable[[RetryCallState], None] = lambda _: None) -> T:
        """Shared concurrency and retry boundary for chat and embeddings."""
        retrying = AsyncRetrying(stop=stop_after_attempt(self.max_retries + 1), wait=wait_exponential(multiplier=.5, max=2),
                                 retry=retry_if_exception(_retryable), before_sleep=before_sleep, reraise=True)
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

    async def _attempt(self, context: PipelineContext, provider: Provider) -> ProviderResult:
        return await provider.chat(messages=context.messages, system=context.system, model=context.request.model, max_tokens=context.request.max_tokens, temperature=context.request.temperature, tools=context.request.tools, tool_choice=context.request.tool_choice, response_format=context.request.response_format, reasoning=context.request.reasoning, cache_system=bool(context.request.cache_system))

    async def run(self, context: PipelineContext) -> None:
        last: BaseException | None = None

        def count_retry(_: RetryCallState) -> None:
            context.retries += 1

        for provider in context.candidates:
            context.provider = provider
            try:
                result = await self.call(provider, lambda: self._attempt(context, provider), context.attempts, before_sleep=count_retry)
            except HTTPException:
                raise
            except Exception as exc:
                last = exc
                if context.request.provider or permanent_client_error(exc): break
                continue
            context.result = result
            if context.request.profile and result.model != context.request.model:
                # A pin mismatch is a configuration fault, not a transient provider
                # fault: surface it as itself rather than as "all providers unavailable".
                raise HTTPException(500, f"chat profile '{context.request.profile}' expected model '{context.request.model}' but provider '{provider.name}' returned '{result.model}'")
            return
        raise provider_failure(last, context.request.provider, context.attempts)
