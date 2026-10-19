import asyncio
from typing import Any

from fastapi import HTTPException
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_exponential

from gateway.llm.orchestration.context import PipelineContext
from gateway.llm.providers.base import Provider, ProviderError, ProviderResult


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, ProviderError) and exc.retryable


class ProviderCallStage:
    def __init__(self, *, max_retries: int = 1, max_concurrency: int = 32) -> None:
        self.max_retries = max_retries; self._semaphore = asyncio.Semaphore(max_concurrency)

    async def _attempt(self, context: PipelineContext, provider: Provider) -> ProviderResult:
        try:
            async with self._semaphore:
                return await provider.chat(messages=context.messages, system=context.system, model=context.request.model, max_tokens=context.request.max_tokens, temperature=context.request.temperature, tools=context.request.tools, tool_choice=context.request.tool_choice, response_format=context.request.response_format, reasoning=context.request.reasoning, cache_system=bool(context.request.cache_system))
        except HTTPException:
            raise
        except BaseException as exc:
            context.attempts.append({"provider": provider.name, "reason": str(exc)[:120]})
            raise

    async def run(self, context: PipelineContext) -> None:
        last: BaseException | None = None

        def count_retry(_: RetryCallState) -> None:
            context.retries += 1

        for provider in context.candidates:
            context.provider = provider
            retrying = AsyncRetrying(stop=stop_after_attempt(self.max_retries + 1), wait=wait_exponential(multiplier=.5, max=2),
                                     retry=retry_if_exception(_retryable), before_sleep=count_retry, reraise=True)
            try:
                result: Any = await retrying(self._attempt, context, provider)
            except HTTPException:
                raise
            except BaseException as exc:
                last = exc
                if context.request.provider: break
                continue
            context.result = result
            if context.request.profile and result.model != context.request.model:
                # A pin mismatch is a configuration fault, not a transient provider
                # fault: surface it as itself rather than as "all providers unavailable".
                raise HTTPException(500, f"chat profile '{context.request.profile}' expected model '{context.request.model}' but provider '{provider.name}' returned '{result.model}'")
            return
        status = last.status if isinstance(last, ProviderError) and context.request.provider else 503
        raise HTTPException(status, f"all providers unavailable. attempts: {context.attempts}. last_error: {last}")
