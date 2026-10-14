from pathlib import Path

from study_system.core.baseline import StudyBaseline
from study_system.core.gateway import GatewayCardGenerator, GatewayQualityChecker, LLMGateway
from study_system.types.mvp import ConceptSummary, GeneratedCard, RetrievedContext


def _baseline(tmp_path: Path) -> StudyBaseline:
    return StudyBaseline(
        daily_card_sets=1,
        cards_per_set=2,
        review_limit=10,
        card_gen_model="test-model",
        feynman_model="test-model",
        challenger_model="test-model",
        prompt_versions={"flashcard": "prompt-v1"},
        database_root=tmp_path,
        sqlite_relative_path="study.db",
    )


def test_gateway_generator_validates_count_and_uses_stable_card_ids(tmp_path: Path) -> None:
    gateway = LLMGateway("http://gateway.invalid")

    def fake_request(method: str, path: str, payload: dict | None = None) -> dict:
        assert method == "POST"
        assert path == "/v1/chat"
        assert payload is not None
        assert payload["response_format"]["schema"]["type"] == "object"
        return {
            "parsed": {
                "cards": [
                    {"front": "Question one?", "back": "Answer one."},
                    {"front": "Question two?", "back": "Answer two."},
                ]
            }
        }

    gateway._request = fake_request  # type: ignore[method-assign]
    generator = GatewayCardGenerator(gateway)
    context = RetrievedContext(
        concept=ConceptSummary(
            id="duration", name="Duration", summary="Rate sensitivity", source_version="v1"
        )
    )

    first = generator.generate(context, 2, _baseline(tmp_path))
    second = generator.generate(context, 2, _baseline(tmp_path))

    assert [card.id for card in first] == [card.id for card in second]
    assert all(card.source_refs for card in first)


def test_gateway_quality_checker_rejects_ungrounded_cards(tmp_path: Path) -> None:
    gateway = LLMGateway("http://gateway.invalid")

    def fake_chat(**kwargs: object) -> dict:
        model_name = kwargs["output_model"].__name__  # type: ignore[union-attr]
        if model_name == "_GroundingOutput":
            prompt = str(kwargs["prompt"])
            return {
                "passed": "Bad question" not in prompt,
                "confidence": 0.9,
                "reason": "fixture",
            }
        return {"scores": {}, "overall": 4.0, "flags": [], "suggestion": None}

    gateway.structured_chat = fake_chat  # type: ignore[method-assign]
    context = RetrievedContext(
        concept=ConceptSummary(id="c1", name="Duration", summary="Ground truth", source_version="v1")
    )
    cards = [
        GeneratedCard(
            id="good",
            concept_id="c1",
            front="Good question?",
            back="Grounded answer",
            card_type="flashcard",
            source_refs=context.source_refs,
            source_version="v1",
            model="test",
            prompt_version="v1",
        ),
        GeneratedCard(
            id="bad",
            concept_id="c1",
            front="Bad question?",
            back="Unsupported answer",
            card_type="flashcard",
            source_refs=context.source_refs,
            source_version="v1",
            model="test",
            prompt_version="v1",
        ),
    ]

    accepted = GatewayQualityChecker(gateway).check(cards, context, _baseline(tmp_path))

    assert [card.id for card in accepted] == ["good"]
