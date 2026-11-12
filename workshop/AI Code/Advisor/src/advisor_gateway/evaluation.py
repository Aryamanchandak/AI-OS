from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .gateway import AdvisorGateway
from .models import (
    AdvisorConfig,
    CompletionProvider,
    CompletionRequest,
    CompletionResponse,
    GatewayUsage,
    IterationUsage,
    ScoreFunction,
)


class EvalArm(str, Enum):
    EXECUTOR_SOLO = "executor_solo"
    EXECUTOR_WITH_ADVISOR = "executor_with_advisor"
    ADVISOR_SOLO = "advisor_solo"


@dataclass(frozen=True, slots=True)
class EvalTask:
    name: str
    request: CompletionRequest
    score: ScoreFunction


@dataclass(frozen=True, slots=True)
class EvalResult:
    task_name: str
    arm: EvalArm
    score: float
    response: CompletionResponse
    usage: GatewayUsage


class EvalHarness:
    def __init__(
        self,
        executor: CompletionProvider,
        advisor: CompletionProvider,
        config: AdvisorConfig,
    ) -> None:
        self.executor = executor
        self.advisor = advisor
        self.config = config

    async def run(self, tasks: tuple[EvalTask, ...]) -> tuple[EvalResult, ...]:
        gateway = AdvisorGateway(self.executor, self.advisor, self.config)
        results: list[EvalResult] = []
        for task in tasks:
            solo_response = await self.executor(task.request)
            solo_usage = GatewayUsage(
                (IterationUsage(1, "executor", task.request.model, solo_response.usage),)
            )
            results.append(
                EvalResult(
                    task.name,
                    EvalArm.EXECUTOR_SOLO,
                    float(task.score(solo_response)),
                    solo_response,
                    solo_usage,
                )
            )

            gateway_result = await gateway.run(task.request)
            results.append(
                EvalResult(
                    task.name,
                    EvalArm.EXECUTOR_WITH_ADVISOR,
                    float(task.score(gateway_result.response)),
                    gateway_result.response,
                    gateway_result.usage,
                )
            )

            advisor_request = task.request.with_changes(
                model=self.config.advisor_model,
                tools=(),
                max_tokens=self.config.max_tokens,
                cache=self.config.caching,
            )
            advisor_response = await self.advisor(advisor_request)
            advisor_usage = GatewayUsage(
                (
                    IterationUsage(
                        1,
                        "advisor",
                        self.config.advisor_model,
                        advisor_response.usage,
                    ),
                )
            )
            results.append(
                EvalResult(
                    task.name,
                    EvalArm.ADVISOR_SOLO,
                    float(task.score(advisor_response)),
                    advisor_response,
                    advisor_usage,
                )
            )
        return tuple(results)
