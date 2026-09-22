import json

from fastapi import HTTPException
from jsonschema import Draft202012Validator, ValidationError

from gateway.llm.orchestration.context import PipelineContext


class StructuredOutputStage:
    async def run(self, context: PipelineContext) -> None:
        if context.output is not None or context.result is None: return
        schema = context.request.response_format.schema_ if context.request.response_format else None
        if not schema or context.result.tool_calls: return
        try:
            parsed = json.loads(context.result.text); Draft202012Validator(schema).validate(parsed)
        except (json.JSONDecodeError, ValidationError) as first_error:
            provider = context.provider
            assert provider is not None
            original = context.result
            repair_messages = [*context.messages, {"role": "assistant", "content": original.text}, {"role": "user", "content": f"Your previous reply did not match the required JSON schema: {first_error}. Reply ONLY with valid JSON conforming to the schema."}]
            context.attempts.append({"provider": provider.name, "reason": "structured-output repair"})
            repaired = await provider.chat(messages=repair_messages, system=context.system, model=context.request.model, max_tokens=context.request.max_tokens, temperature=0, response_format=context.request.response_format)
            repaired.usage.input_tokens += original.usage.input_tokens
            repaired.usage.output_tokens += original.usage.output_tokens
            repaired.usage.cache_creation_input_tokens += original.usage.cache_creation_input_tokens
            repaired.usage.cache_read_input_tokens += original.usage.cache_read_input_tokens
            context.result = repaired
            try:
                parsed = json.loads(repaired.text); Draft202012Validator(schema).validate(parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                raise HTTPException(502, f"provider returned invalid structured output after repair: {exc}") from exc
        context.result.raw["parsed"] = parsed
