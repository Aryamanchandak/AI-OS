from fastapi import HTTPException

from gateway.llm.models import ChatRequest
from gateway.llm.orchestration.context import PipelineContext


def _validate_schema_size(value: object, *, depth: int = 0, counter: list[int] | None = None) -> None:
    count = counter if counter is not None else [0]
    count[0] += 1
    if depth > 40: raise HTTPException(400, "response schema exceeds maximum depth 40")
    if count[0] > 5000: raise HTTPException(400, "response schema exceeds maximum node count 5000")
    if isinstance(value, dict):
        for item in value.values(): _validate_schema_size(item, depth=depth + 1, counter=count)
    elif isinstance(value, list):
        for item in value: _validate_schema_size(item, depth=depth + 1, counter=count)


class RequestValidationStage:
    async def run(self, context: PipelineContext) -> None:
        request: ChatRequest = context.request
        if request.profile and (request.provider or request.model or request.auto_route):
            raise HTTPException(400, "chat profile is mutually exclusive with provider/model/auto_route")
        if request.messages is None and request.prompt is None:
            raise HTTPException(400, "either messages or prompt is required")
        if request.max_tokens <= 0:
            raise HTTPException(400, "max_tokens must be positive")
        if request.response_format and request.response_format.schema_:
            _validate_schema_size(request.response_format.schema_)
