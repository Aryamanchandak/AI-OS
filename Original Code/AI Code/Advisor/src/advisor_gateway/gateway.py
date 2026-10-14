from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .accounting import IterationRecorder
from .models import (
    AdvisorConfig,
    CompletionProvider,
    CompletionRequest,
    CompletionResponse,
    GatewayResult,
    GatewayUsage,
    IterationRole,
    IterationUsage,
)
from .prompting import ADVISOR_SYSTEM_PROMPT, EXECUTOR_TIMING_PROMPT
from .serializer import serialize_transcript


class AdvisorLimitError(RuntimeError):
    pass


class AdvisorResponseError(RuntimeError):
    pass


@dataclass(slots=True)
class _RunState:
    request_id: str
    recorder: IterationRecorder | None
    iterations: list[IterationUsage]

    def add(self, role: IterationRole, model: str, response: CompletionResponse) -> None:
        item = IterationUsage(len(self.iterations) + 1, role, model, response.usage)
        self.iterations.append(item)
        if self.recorder is not None:
            self.recorder.record(self.request_id, item)


class AdvisorGateway:
    def __init__(
        self,
        executor: CompletionProvider,
        advisor: CompletionProvider,
        config: AdvisorConfig,
        recorder: IterationRecorder | None = None,
    ) -> None:
        self.executor = executor
        self.advisor = advisor
        self.config = config
        self.recorder = recorder

    @property
    def advisor_tool(self) -> Mapping[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        if self.config.dummy_input_field is not None:
            properties[self.config.dummy_input_field] = {
                "type": "string",
                "description": "Compatibility placeholder; its value is ignored.",
            }
            required.append(self.config.dummy_input_field)
        return {
            "name": "advisor",
            "description": "Consult a stronger, toolless reviewer over the full transcript.",
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        }

    async def run(
        self,
        request: CompletionRequest,
        *,
        request_id: str | None = None,
    ) -> GatewayResult:
        run_id = request_id or uuid4().hex
        state = _RunState(run_id, self.recorder, [])
        working = self._prepare_request(request)
        advisor_uses = 0
        limit_feedback_sent = False

        while True:
            response = await self.executor(working)
            state.add("executor", working.model, response)
            tool_calls = [block for block in response.content if block.get("type") == "tool_use"]
            advisor_calls = [block for block in tool_calls if block.get("name") == "advisor"]

            if not advisor_calls or len(advisor_calls) != len(tool_calls):
                return GatewayResult(
                    response=response,
                    usage=GatewayUsage(tuple(state.iterations)),
                    request_id=run_id,
                )

            call_ids: list[str] = []
            for call in advisor_calls:
                tool_use_id = call.get("id")
                if not isinstance(tool_use_id, str) or not tool_use_id:
                    raise ValueError("advisor tool_use blocks require a non-empty string id")
                if tool_use_id in call_ids:
                    raise ValueError("advisor tool_use ids must be unique within a response")
                self._validate_advisor_input(call)
                call_ids.append(tool_use_id)

            if advisor_uses >= self.config.max_uses:
                if limit_feedback_sent:
                    raise AdvisorLimitError(
                        "Executor repeatedly requested the advisor after max_uses was exhausted"
                    )
                advice = (
                    "Advisor consultation budget exhausted. Continue independently and produce "
                    "the best final result from the evidence already available."
                )
                limit_feedback_sent = True
            else:
                advisor_response = await self._consult(working, response)
                state.add("advisor", self.config.advisor_model, advisor_response)
                advice = _text_only(advisor_response)
                advisor_uses += 1

            results: list[Mapping[str, Any]] = []
            for tool_use_id in call_ids:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": advice,
                    }
                )

            working = working.with_changes(
                messages=working.messages
                + ({"role": "assistant", "content": response.content},)
                + ({"role": "user", "content": tuple(results)},)
            )

    def _validate_advisor_input(self, call: Mapping[str, Any]) -> None:
        value = call.get("input")
        if not isinstance(value, Mapping):
            raise ValueError("advisor tool input must be an object")
        dummy = self.config.dummy_input_field
        if dummy is None:
            if value:
                raise ValueError("advisor tool input must be empty")
            return
        if set(value) != {dummy} or not isinstance(value[dummy], str):
            raise ValueError(
                f"advisor tool input must contain only the string field {dummy!r}"
            )

    def _prepare_request(self, request: CompletionRequest) -> CompletionRequest:
        if any(tool.get("name") == "advisor" for tool in request.tools):
            raise ValueError("Request already defines a tool named 'advisor'")
        system = request.system
        if self.config.inject_executor_prompt:
            system = f"{system}\n\n{EXECUTOR_TIMING_PROMPT}" if system else EXECUTOR_TIMING_PROMPT
        return request.with_changes(system=system, tools=request.tools + (self.advisor_tool,))

    async def _consult(
        self,
        executor_request: CompletionRequest,
        partial_response: CompletionResponse,
    ) -> CompletionResponse:
        context = serialize_transcript(executor_request, partial_response)
        advisor_request = CompletionRequest(
            model=self.config.advisor_model,
            system=ADVISOR_SYSTEM_PROMPT,
            messages=({"role": "user", "content": ({"type": "text", "text": context},)},),
            tools=(),
            max_tokens=self.config.max_tokens,
            cache=self.config.caching,
            metadata={"purpose": "advisor_consultation"},
        )
        return await self.advisor(advisor_request)


def _text_only(response: CompletionResponse) -> str:
    parts = [block.get("text") for block in response.content if block.get("type") == "text"]
    text = "\n".join(part for part in parts if isinstance(part, str) and part.strip()).strip()
    if not text:
        raise AdvisorResponseError("Advisor returned no textual guidance")
    return text
