import asyncio

from fastapi import HTTPException

from gateway.llm.orchestration.context import PipelineContext
from gateway.llm.providers.base import ProviderError


class ProviderCallStage:
    def __init__(self, *, max_retries: int = 1, max_concurrency: int = 32) -> None:
        self.max_retries = max_retries; self._semaphore = asyncio.Semaphore(max_concurrency)

    async def run(self, context: PipelineContext) -> None:
        if context.output is not None: return
        last: BaseException | None = None
        for provider in context.candidates:
            context.provider = provider
            for retry in range(self.max_retries + 1):
                try:
                    async with self._semaphore:
                        context.result = await provider.chat(messages=context.messages, system=context.system, model=context.request.model, max_tokens=context.request.max_tokens, temperature=context.request.temperature, tools=context.request.tools, tool_choice=context.request.tool_choice, response_format=context.request.response_format, reasoning=context.request.reasoning)
                    if context.request.profile and context.result.model != context.request.model:
                        raise ProviderError(f"chat profile '{context.request.profile}' expected model '{context.request.model}' but provider '{provider.name}' returned '{context.result.model}'", status=500)
                    return
                except BaseException as exc:
                    last = exc; context.attempts.append({"provider": provider.name, "reason": str(exc)[:120]})
                    retryable = isinstance(exc, ProviderError) and exc.retryable
                    if retry < self.max_retries and retryable:
                        context.retries += 1; await asyncio.sleep(min(2.0, .5 * (2 ** retry))); continue
                    break
            if context.request.provider: break
        status = last.status if isinstance(last, ProviderError) and context.request.provider else 503
        raise HTTPException(status, f"all providers unavailable. attempts: {context.attempts}. last_error: {last}")
