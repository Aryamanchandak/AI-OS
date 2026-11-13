from __future__ import annotations

import json
import re
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from ...config import PROJECT_ROOT, Settings
from ...metering import UsageLedger

T = TypeVar("T", bound=BaseModel)

# Highest ``max_output_tokens`` the 2.5 and 3.x Gemini families accept.
OUTPUT_TOKEN_CEILING = 65_536

_FENCE = re.compile(r"\A\s*```(?:json)?\s*|\s*```\s*\Z", re.I)

# These constraints are still enforced by Pydantic after decoding.  Sending
# large array bounds and string/number matchers to Gemini, however, expands
# its constrained-decoding state machine enough for the API to reject complex
# response schemas with INVALID_ARGUMENT.
_SERVING_EXPENSIVE_SCHEMA_KEYS = frozenset({
    "minItems", "maxItems", "minLength", "maxLength", "pattern", "format",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
})


class ConfigurationError(RuntimeError):
    pass


class ModelResponseError(RuntimeError):
    """A call came back without a usable payload; ``detail`` is the audit record."""

    def __init__(self, message: str, detail: dict[str, Any]):
        super().__init__(message)
        self.detail = detail


class ModelClient(Protocol):
    def generate(self, *, run_id: str, stage: str, prompt_name: str, prompt_data: str, schema: type[T], model_tier: str = "fast", retry_count: int = 0) -> T: ...


def load_prompt(name: str) -> tuple[str, str]:
    path = PROJECT_ROOT / "src" / "consequence_radar" / name
    text = path.read_text(encoding="utf-8")
    first = text.splitlines()[0] if text else ""
    version = first.removeprefix("<!-- version:").removesuffix(" -->").strip() if first.startswith("<!-- version:") else "1"
    return text, version


def _enum_name(value: Any) -> str | None:
    """Gemini enums arrive as enum members locally and as plain strings over the wire."""
    if value is None:
        return None
    return str(getattr(value, "name", value))


def response_text(response: Any) -> str:
    """Concatenate the answer parts, skipping the model's private thought parts."""
    chunks: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)
    if chunks:
        return "".join(chunks)
    # Stubs and older payload shapes expose the body only as ``.text``.
    return getattr(response, "text", None) or ""


def decode_payload(text: str) -> Any:
    return json.loads(_FENCE.sub("", text.strip()))


def response_json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Return a Gemini-safe structured-output schema.

    Pydantic remains the authoritative validator for every constraint.  This
    transport copy preserves the JSON shape, required fields, enums, and
    dictionary value schemas while omitting constraints that make Gemini's
    serving automaton impractically large.
    """
    def simplify(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: simplify(item)
                for key, item in value.items()
                if key not in _SERVING_EXPENSIVE_SCHEMA_KEYS
            }
        if isinstance(value, list):
            return [simplify(item) for item in value]
        return value

    return simplify(schema.model_json_schema())


def _validation_summary(error: ValidationError) -> str:
    parts = [f"{'.'.join(str(x) for x in e['loc']) or '<root>'}: {e['msg']}" for e in error.errors()[:3]]
    extra = error.error_count() - len(parts)
    return "; ".join(parts) + (f" (+{extra} more)" if extra > 0 else "")


class GeminiModelClient:
    def __init__(self, settings: Settings, ledger: UsageLedger, on_call=None):
        if not settings.api_key:
            raise ConfigurationError("GEMINI_API_KEY or GOOGLE_API_KEY is required for a real run")
        from google import genai
        self.settings, self.ledger, self.on_call = settings, ledger, on_call
        self.client = genai.Client(api_key=settings.api_key)

    def _audit(self, record: dict[str, Any]) -> None:
        if self.on_call:
            self.on_call(record)

    def generate(self, *, run_id: str, stage: str, prompt_name: str, prompt_data: str, schema: type[T], model_tier: str = "fast", retry_count: int = 0) -> T:
        from google.genai import types
        instruction, version = load_prompt(prompt_name)
        model = {"fast": self.settings.fast_model, "reasoning": self.settings.reasoning_model, "report": self.settings.report_model}[model_tier]
        contents = f"{instruction}\n\n<INPUT_DATA>\n{prompt_data}\n</INPUT_DATA>"
        budget = min(self.settings.max_output_tokens, OUTPUT_TOKEN_CEILING)
        failure: ModelResponseError | None = None

        for offset in range(2):
            self.ledger.guard_external_call()
            audit: dict[str, Any] = {"run_id": run_id, "stage": stage, "model_name": model, "prompt_version": version, "input_tokens": 0, "output_tokens": 0, "retry_count": retry_count + offset, "max_output_tokens": budget}
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        # Gemini Developer API rejects dictionary-valued
                        # ``additionalProperties`` while converting a Pydantic
                        # model through response_schema.  response_json_schema is
                        # the native JSON Schema path and supports those models.
                        response_json_schema=response_json_schema(schema),
                        temperature=0.1,
                        max_output_tokens=budget,
                        # Nothing here is a callable tool, and leaving this unset
                        # makes the SDK log an automatic-function-calling warning
                        # on every single request.
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    ),
                )
            except Exception as exc:
                audit["error"] = str(exc)
                self._audit(audit)
                raise

            usage = getattr(response, "usage_metadata", None)
            inp = int(getattr(usage, "prompt_token_count", 0) or 0)
            out = int(getattr(usage, "candidates_token_count", 0) or 0)
            thinking = int(getattr(usage, "thoughts_token_count", 0) or 0)
            self.ledger.record(inp, out)
            finish = _enum_name(next((getattr(c, "finish_reason", None) for c in getattr(response, "candidates", None) or []), None)) or "UNKNOWN"
            blocked = _enum_name(getattr(getattr(response, "prompt_feedback", None), "block_reason", None))
            audit.update({"input_tokens": inp, "output_tokens": out, "thinking_tokens": thinking, "finish_reason": finish})
            if blocked:
                audit["block_reason"] = blocked

            # ``response.parsed`` is left as None whenever the body fails to
            # decode -- the SDK swallows the JSONDecodeError -- so parse the raw
            # text here and keep the reason the parse failed.
            text = response_text(response)
            problem: str | None = None
            payload: Any = None
            if not text.strip():
                problem = f"the model returned an empty body (finish_reason={finish}" + (f", block_reason={blocked}" if blocked else "") + ")"
            else:
                try:
                    payload = decode_payload(text)
                except json.JSONDecodeError as exc:
                    problem = f"the response body is not valid JSON ({exc})"

            if problem is None:
                try:
                    result = schema.model_validate(payload)
                except ValidationError as exc:
                    problem = f"the response JSON does not match {schema.__name__} ({_validation_summary(exc)})"
                else:
                    self._audit(audit)
                    return result

            if finish == "MAX_TOKENS":
                problem += f"; output was truncated at max_output_tokens={budget} after {thinking} thinking tokens"
            audit["error"] = problem
            audit["response_tail"] = text[-400:]
            self._audit(audit)
            failure = ModelResponseError(f"{stage} returned no usable structured response: {problem}", audit)
            if finish == "MAX_TOKENS":
                # max_output_tokens is already far above what any schema here
                # needs, so a truncated body means the generation ran away.  A
                # re-ask at temperature 0.1 reproduces it and burns minutes of
                # the wall-clock budget, which would bury this error under a
                # BudgetExceeded further down the pipeline.  Fail now instead.
                break

        raise failure
