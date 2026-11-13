import json

import pytest
from types import SimpleNamespace

from consequence_radar.models import CandidateSelection
from consequence_radar.providers.model import (
    OUTPUT_TOKEN_CEILING,
    GeminiModelClient,
    ModelResponseError,
    response_json_schema,
)


class StubLedger:
    def __init__(self):
        self.recorded = None
        self.calls = 0

    def guard_external_call(self):
        self.calls += 1

    def record(self, input_tokens, output_tokens):
        self.recorded = (input_tokens, output_tokens)


def response(text, *, finish_reason="STOP", prompt_tokens=7, output_tokens=3, thinking_tokens=0):
    parts = [SimpleNamespace(text=text, thought=False)] if text is not None else []
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=parts),
                finish_reason=SimpleNamespace(name=finish_reason),
            )
        ],
        prompt_feedback=None,
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=output_tokens,
            thoughts_token_count=thinking_tokens,
        ),
    )


class StubModels:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.configs = []

    def generate_content(self, *, model, contents, config):
        self.configs.append(config)
        return self.responses[min(len(self.configs), len(self.responses)) - 1]

    @property
    def config(self):
        return self.configs[-1]


def make_client(models, ledger, on_call=None, max_output_tokens=32_768):
    client = object.__new__(GeminiModelClient)
    client.settings = SimpleNamespace(
        fast_model="gemini-test",
        reasoning_model="gemini-test",
        report_model="gemini-test",
        max_output_tokens=max_output_tokens,
    )
    client.ledger = ledger
    client.on_call = on_call
    client.client = SimpleNamespace(models=models)
    return client


def generate(client):
    return client.generate(
        run_id="run-1",
        stage="candidate_selection",
        prompt_name="candidate_selector.md",
        prompt_data="{}",
        schema=CandidateSelection,
    )


@pytest.fixture(autouse=True)
def stub_prompt(monkeypatch):
    monkeypatch.setattr(
        "consequence_radar.providers.model.gemini.load_prompt",
        lambda name: ("Select candidates.", "test"),
    )


def test_generate_uses_native_json_schema_for_dictionary_fields():
    ledger = StubLedger()
    models = StubModels(response(json.dumps({"candidates": []})))
    result = generate(make_client(models, ledger))

    assert isinstance(result, CandidateSelection)
    assert models.config.response_schema is None
    grades_schema = models.config.response_json_schema["$defs"]["CandidateSeed"]["properties"]["grades"]
    assert grades_schema["additionalProperties"]["enum"] == ["low", "medium", "high"]
    assert models.config.automatic_function_calling.disable is True
    assert ledger.recorded == (7, 3)


def test_wire_schema_omits_constraints_that_overflow_gemini_state_limits():
    wire_schema = response_json_schema(CandidateSelection)

    claims = wire_schema["properties"]["claims"]
    assert "maxItems" not in claims
    assert "minLength" not in wire_schema["$defs"]["CandidateSeed"]["properties"]["reported_premise"]
    # The output shape and enum constraints are still supplied to Gemini.
    assert claims["items"] == {"$ref": "#/$defs/CandidateSeed"}
    assert wire_schema["$defs"]["CandidateSeed"]["properties"]["grades"]["additionalProperties"]["enum"] == ["low", "medium", "high"]


def test_generate_parses_a_fenced_body():
    body = "```json\n" + json.dumps({"candidates": []}) + "\n```"
    result = generate(make_client(StubModels(response(body)), StubLedger()))
    assert isinstance(result, CandidateSelection)


def test_a_transient_bad_body_is_retried_once():
    calls = []
    models = StubModels(response("not json at all"), response(json.dumps({"candidates": []})))
    result = generate(make_client(models, StubLedger(), on_call=calls.append))

    assert isinstance(result, CandidateSelection)
    assert len(models.configs) == 2
    assert calls[0]["retry_count"] == 0 and calls[1]["retry_count"] == 1
    assert "not valid JSON" in calls[0]["error"]


def test_truncated_output_fails_fast_without_burning_a_retry():
    # A runaway generation reproduces on a re-ask and costs minutes of the
    # wall-clock budget, so truncation must not consume a second call.
    calls = []
    models = StubModels(response('{"candidates": [', finish_reason="MAX_TOKENS", thinking_tokens=2400))
    client = make_client(models, StubLedger(), on_call=calls.append, max_output_tokens=32_768)

    with pytest.raises(ModelResponseError) as excinfo:
        generate(client)

    assert len(models.configs) == 1
    assert "candidate_selection returned no usable structured response" in str(excinfo.value)
    assert "truncated at max_output_tokens=32768 after 2400 thinking tokens" in str(excinfo.value)
    assert excinfo.value.detail["finish_reason"] == "MAX_TOKENS"
    assert excinfo.value.detail["thinking_tokens"] == 2400
    assert excinfo.value.detail["response_tail"] == '{"candidates": ['
    assert len(calls) == 1


def test_configured_budget_is_clamped_to_the_api_ceiling():
    models = StubModels(response(json.dumps({"candidates": []})))
    generate(make_client(models, StubLedger(), max_output_tokens=OUTPUT_TOKEN_CEILING * 4))
    assert models.config.max_output_tokens == OUTPUT_TOKEN_CEILING


def test_empty_body_reports_the_finish_reason():
    with pytest.raises(ModelResponseError) as excinfo:
        generate(make_client(StubModels(response(None, finish_reason="SAFETY")), StubLedger()))
    assert "empty body (finish_reason=SAFETY)" in str(excinfo.value)


def test_schema_mismatch_names_the_offending_field():
    body = json.dumps({"candidates": [{"id": "C1"}]})
    with pytest.raises(ModelResponseError) as excinfo:
        generate(make_client(StubModels(response(body)), StubLedger()))
    assert "does not match CandidateSelection" in str(excinfo.value)
    assert "candidates.0." in str(excinfo.value)


def test_transport_errors_are_audited_and_reraised():
    calls = []

    class Boom:
        def generate_content(self, **kwargs):
            raise RuntimeError("404 NOT_FOUND")

    with pytest.raises(RuntimeError, match="404 NOT_FOUND"):
        generate(make_client(Boom(), StubLedger(), on_call=calls.append))
    assert calls[0]["error"] == "404 NOT_FOUND"
