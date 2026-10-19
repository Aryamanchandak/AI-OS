from fastapi import HTTPException

from gateway.llm.models import ChatRequest
from gateway.llm.orchestration.context import PipelineContext
from gateway.llm.providers.content import content_has_image


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
        if request.profile and (request.provider or request.model):
            raise HTTPException(400, "chat profile is mutually exclusive with provider/model")
        if request.messages is None and request.prompt is None:
            raise HTTPException(400, "either messages or prompt is required")
        if request.max_tokens <= 0:
            raise HTTPException(400, "max_tokens must be positive")
        if request.response_format and request.response_format.schema_:
            _validate_schema_size(request.response_format.schema_)


def validate_vision_candidates(context: PipelineContext) -> None:
    """Check resolved candidates before budget admission or provider execution."""
    if not any(content_has_image(message.get("content")) for message in context.messages):
        return
    context.candidates = [provider for provider in context.candidates if provider.capabilities.vision]
    if not context.candidates:
        raise HTTPException(400, "Images require a vision-capable model; choose a vision-capable provider or profile")
