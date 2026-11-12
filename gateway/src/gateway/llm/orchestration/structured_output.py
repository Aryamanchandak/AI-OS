import json

from fastapi import HTTPException
from jsonschema import Draft202012Validator, ValidationError

from gateway.llm.orchestration.context import PipelineContext


class StructuredOutputStage:
    async def run(self, context: PipelineContext) -> None:
        if context.result is None: return
        if context.request.response_format is None or context.result.tool_calls: return
        schema = context.request.response_format.schema_
        try:
            parsed = json.loads(context.result.text)
            if schema is not None:
                Draft202012Validator(schema).validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(502, f"provider returned invalid structured output: {exc}") from exc
        context.result.raw["parsed"] = parsed
