from unified_ingestion.extraction import GatewaySemanticExtractor


def test_gateway_extraction_validates_and_links_verbatim_evidence() -> None:
    extractor = GatewaySemanticExtractor("http://gateway.invalid")

    def fake_chat(prompt: str) -> dict:
        assert "Duration measures rate sensitivity." in prompt
        return {
            "concepts": [
                {
                    "label": "Duration",
                    "aliases": [],
                    "confidence": 0.95,
                    "evidence_quote": "Duration",
                }
            ],
            "claims": [
                {
                    "text": "Duration measures rate sensitivity.",
                    "concept_labels": ["Duration"],
                    "confidence": 0.95,
                    "evidence_quote": "Duration measures rate sensitivity.",
                }
            ],
            "relations": [],
            "field_tags": ["fixed_income"],
            "source_quality_signals": [],
            "overall_confidence": 0.95,
        }

    extractor._chat = fake_chat  # type: ignore[method-assign]
    content = "Duration measures rate sensitivity.\n"
    first = extractor.extract(
        source_record_id="source-1", normalized_content=content, metadata={}
    )
    second = extractor.extract(
        source_record_id="source-1", normalized_content=content, metadata={}
    )

    evidence = first.semantic.claims[0].evidence[0]
    assert evidence.normalized_char_start == 0
    assert evidence.normalized_char_end == len("Duration measures rate sensitivity.")
    assert first.semantic.claims[0].proposal_id == second.semantic.claims[0].proposal_id
    assert first.review_reasons == []


def test_non_verbatim_model_evidence_is_sent_to_review() -> None:
    extractor = GatewaySemanticExtractor("http://gateway.invalid")
    extractor._chat = lambda prompt: {  # type: ignore[method-assign]
        "concepts": [],
        "claims": [
            {
                "text": "Paraphrased claim",
                "concept_labels": [],
                "confidence": 0.9,
                "evidence_quote": "not in the source",
            }
        ],
        "relations": [],
        "field_tags": [],
        "source_quality_signals": [],
        "overall_confidence": 0.9,
    }
    result = extractor.extract(
        source_record_id="source-1", normalized_content="Actual source", metadata={}
    )
    assert "unresolved_evidence_quote" in result.review_reasons
