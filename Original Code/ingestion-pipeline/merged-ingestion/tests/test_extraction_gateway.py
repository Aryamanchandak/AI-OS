from __future__ import annotations

import pytest

from ingestion.extraction.base import ExtractionError, HighlightExtractionInput
from ingestion.extraction.gateway import DEFAULT_BATCH_MAX_TOKENS, GatewayExtractor
from ingestion.extraction.prompts import EXTRACTION_PROMPT_TEMPLATE


class FakeChatClient:
    def __init__(self, response: dict | None = None, *, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def chat(
        self,
        prompt=None,
        *,
        system=None,
        profile=None,
        provider=None,
        max_tokens=2048,
        temperature=0.7,
        response_format=None,
    ):
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "profile": profile,
                "provider": provider,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        if self.error is not None:
            raise self.error
        return self.response


def _payload(**overrides) -> dict:
    payload = {
        "concepts": [],
        "claims": [],
        "relations": [],
        "field_tags": [],
        "source_quality_signals": [],
        "overall_confidence": 0.9,
    }
    payload.update(overrides)
    return payload


def test_maps_parsed_payload_and_locates_evidence_verbatim() -> None:
    content = "Duration measures interest rate sensitivity. Convexity refines it."
    client = FakeChatClient(
        response={
            "parsed": _payload(
                concepts=[
                    {
                        "label": "Duration",
                        "aliases": ["DUR"],
                        "confidence": 0.9,
                        "evidence_quotes": ["Duration measures interest rate sensitivity."],
                    }
                ],
                claims=[
                    {
                        "text": "Duration measures rate sensitivity.",
                        "concept_labels": ["Duration"],
                        "confidence": 0.8,
                        "evidence_quotes": ["Convexity refines it."],
                    }
                ],
                relations=[
                    {
                        "subject": "Convexity",
                        "predicate": "REFINES",
                        "object": "Duration",
                        "confidence": 0.7,
                        "evidence_quotes": ["Convexity refines it."],
                    }
                ],
                field_tags=["fixed_income"],
            )
        }
    )

    result = GatewayExtractor(chat_client=client).extract(
        source_record_id="source-1", normalized_content=content, metadata={}
    )

    assert result.model_confidence == 0.9
    assert result.review_reasons == []
    concept = result.semantic.concepts[0]
    assert concept.proposal_id == "concept-source-1-0"
    assert concept.label == "Duration"
    assert concept.aliases == ["DUR"]
    assert concept.model_confidence == 0.9
    assert concept.evidence[0].quote == "Duration measures interest rate sensitivity."
    assert concept.evidence[0].normalized_char_start == 0
    assert concept.evidence[0].normalized_char_end == len(
        "Duration measures interest rate sensitivity."
    )

    claim = result.semantic.claims[0]
    assert claim.proposal_id == "claim-source-1-0"
    assert claim.evidence[0].quote == "Convexity refines it."

    relation = result.semantic.relations[0]
    assert relation.proposal_id == "relation-source-1-0"
    assert relation.subject == "Convexity"
    assert relation.predicate == "REFINES"
    assert relation.hierarchical is False  # default when the gateway omits it
    assert result.semantic.field_tags == ["fixed_income"]


def test_relation_hierarchical_flag_flows_through_when_the_model_sets_it() -> None:
    content = "X is strictly a prerequisite of Y."
    client = FakeChatClient(
        response={
            "parsed": _payload(
                relations=[
                    {
                        "subject": "X",
                        "predicate": "PREREQUISITE_OF",
                        "object": "Y",
                        "confidence": 0.9,
                        "evidence_quotes": ["X is strictly a prerequisite of Y."],
                        "hierarchical": True,
                    }
                ],
            )
        }
    )

    result = GatewayExtractor(chat_client=client).extract(
        source_record_id="source-1", normalized_content=content, metadata={}
    )

    assert result.semantic.relations[0].hierarchical is True


def test_empty_extraction_cannot_be_recorded_as_high_confidence() -> None:
    client = FakeChatClient(response={"parsed": _payload(overall_confidence=1.0)})

    result = GatewayExtractor(chat_client=client).extract(
        source_record_id="source-empty",
        normalized_content="This is a clear factual sentence.",
        metadata={},
    )

    assert result.semantic.concepts == []
    assert result.semantic.claims == []
    assert result.semantic.relations == []
    assert result.model_confidence == 0.0


def test_non_verbatim_quote_is_dropped_not_invented() -> None:
    content = "Duration measures interest rate sensitivity."
    client = FakeChatClient(
        response={
            "parsed": _payload(
                concepts=[
                    {
                        "label": "Duration",
                        "confidence": 0.9,
                        "evidence_quotes": ["Duration measures how sensitive rates are"],
                    }
                ],
            )
        }
    )

    result = GatewayExtractor(chat_client=client).extract(
        source_record_id="source-1", normalized_content=content, metadata={}
    )

    assert result.semantic.concepts[0].evidence == []


def test_gateway_profile_owns_provider_selection_and_structured_output() -> None:
    content = "Duration measures interest rate sensitivity."
    client = FakeChatClient(response={"parsed": _payload()})

    GatewayExtractor(chat_client=client).extract(
        source_record_id="source-1", normalized_content=content, metadata={}
    )

    call = client.calls[0]
    assert call["provider"] is None
    assert call["profile"] == "knowledge-extraction-v1"
    assert call["system"]
    assert content in call["prompt"]
    assert call["response_format"]["type"] == "json_schema"
    assert "schema" in call["response_format"]


def test_prompt_restricts_aliases_and_source_quality_to_evidenced_problems() -> None:
    assert "alias ONLY when the passage explicitly states" in EXTRACTION_PROMPT_TEMPLATE
    assert "passage is short" in EXTRACTION_PROMPT_TEMPLATE
    assert "faithfully preserved qualification is not" in EXTRACTION_PROMPT_TEMPLATE


def test_gateway_call_error_raises_extraction_error() -> None:
    client = FakeChatClient(error=RuntimeError("gateway unreachable"))

    with pytest.raises(ExtractionError, match="Gateway extraction call failed"):
        GatewayExtractor(chat_client=client).extract(
            source_record_id="source-1", normalized_content="text", metadata={}
        )


def test_missing_parsed_field_raises_extraction_error() -> None:
    client = FakeChatClient(response={"text": "not structured"})

    with pytest.raises(ExtractionError, match="did not return structured output"):
        GatewayExtractor(chat_client=client).extract(
            source_record_id="source-1", normalized_content="text", metadata={}
        )


def test_schema_invalid_payload_raises_extraction_error() -> None:
    client = FakeChatClient(response={"parsed": {"overall_confidence": 1.5}})

    with pytest.raises(ExtractionError, match="failed schema validation"):
        GatewayExtractor(chat_client=client).extract(
            source_record_id="source-1", normalized_content="text", metadata={}
        )


# --------------------------------------------------------------------------
# Batched extraction (T33): several highlights, one call, verified mapping back
# --------------------------------------------------------------------------


def _item(batch_item_id: str, text: str, *, index: int = 0, context: str | None = None):
    return HighlightExtractionInput(
        batch_item_id=batch_item_id,
        source_record_id="source-1",
        highlight_index=index,
        highlight_text=text,
        context_text=context,
    )


def _highlight_payload(batch_item_id: str, **overrides) -> dict:
    return {"batch_item_id": batch_item_id, **_payload(**overrides)}


def test_batch_maps_each_payload_back_to_its_own_highlight() -> None:
    first = "Duration measures interest rate sensitivity."
    second = "Convexity refines the duration estimate."
    client = FakeChatClient(
        response={
            "parsed": {
                # Deliberately out of order: the id is the mapping, not position.
                "items": [
                    _highlight_payload(
                        "h1",
                        concepts=[
                            {
                                "label": "Convexity",
                                "confidence": 0.9,
                                "evidence_quotes": [second],
                            }
                        ],
                    ),
                    _highlight_payload(
                        "h0",
                        concepts=[
                            {
                                "label": "Duration",
                                "confidence": 0.9,
                                "evidence_quotes": [first],
                            }
                        ],
                    ),
                ]
            }
        }
    )

    results = GatewayExtractor(chat_client=client).extract_batch(
        [_item("h0", first, index=0), _item("h1", second, index=1)]
    )

    assert len(client.calls) == 1
    assert set(results) == {"h0", "h1"}
    assert results["h0"].semantic.concepts[0].label == "Duration"
    assert results["h1"].semantic.concepts[0].label == "Convexity"
    # Evidence is located in each highlight's own text, so offsets are local.
    assert results["h0"].semantic.concepts[0].evidence[0].normalized_char_start == 0
    assert results["h1"].semantic.concepts[0].evidence[0].quote == second


def test_a_quote_from_the_context_is_dropped_not_credited_to_the_highlight() -> None:
    highlight = "It refines the duration estimate."
    client = FakeChatClient(
        response={
            "parsed": {
                "items": [
                    _highlight_payload(
                        "h0",
                        concepts=[
                            {
                                "label": "Convexity",
                                "confidence": 0.9,
                                # Present in the context, absent from the highlight.
                                "evidence_quotes": ["Convexity is a second-order measure."],
                            }
                        ],
                    )
                ]
            }
        }
    )

    results = GatewayExtractor(chat_client=client).extract_batch(
        [_item("h0", highlight, context="Convexity is a second-order measure. […]")]
    )

    assert results["h0"].semantic.concepts[0].evidence == []


def test_a_missing_payload_fails_loud_rather_than_mismapping() -> None:
    client = FakeChatClient(
        response={"parsed": {"items": [_highlight_payload("h0")]}}
    )

    with pytest.raises(ExtractionError, match="missing=\\['h1'\\]"):
        GatewayExtractor(chat_client=client).extract_batch(
            [_item("h0", "First."), _item("h1", "Second.", index=1)]
        )


def test_a_duplicated_payload_fails_loud() -> None:
    client = FakeChatClient(
        response={
            "parsed": {"items": [_highlight_payload("h0"), _highlight_payload("h0")]}
        }
    )

    with pytest.raises(ExtractionError, match="duplicate batch_item_id"):
        GatewayExtractor(chat_client=client).extract_batch(
            [_item("h0", "First."), _item("h1", "Second.", index=1)]
        )


def test_an_unrecognized_payload_id_fails_loud() -> None:
    client = FakeChatClient(
        response={"parsed": {"items": [_highlight_payload("h0"), _highlight_payload("h7")]}}
    )

    with pytest.raises(ExtractionError, match="unexpected=\\['h7'\\]"):
        GatewayExtractor(chat_client=client).extract_batch(
            [_item("h0", "First."), _item("h1", "Second.", index=1)]
        )


def test_batch_prompt_labels_each_highlight_and_forbids_quoting_the_context() -> None:
    client = FakeChatClient(response={"parsed": {"items": [_highlight_payload("h0")]}})

    GatewayExtractor(chat_client=client).extract_batch(
        [_item("h0", "The highlight body.", context="Leading context. […]")]
    )

    prompt = client.calls[0]["prompt"]
    assert "id: h0" in prompt
    assert "The highlight body." in prompt
    assert "Leading context." in prompt
    assert "NEVER quote from the context" in prompt


def test_batch_uses_the_larger_output_budget() -> None:
    client = FakeChatClient(response={"parsed": {"items": [_highlight_payload("h0")]}})

    GatewayExtractor(chat_client=client).extract_batch([_item("h0", "Body.")])

    assert client.calls[0]["max_tokens"] == DEFAULT_BATCH_MAX_TOKENS


def test_an_empty_batch_makes_no_call() -> None:
    client = FakeChatClient(response={"parsed": {"items": []}})

    assert GatewayExtractor(chat_client=client).extract_batch([]) == {}
    assert client.calls == []
