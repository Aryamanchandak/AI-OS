"""Tests for the parse step: document -> ordered highlights with real context."""

from __future__ import annotations

import pytest

from gateway.ingestion.config import SegmentationConfig
from gateway.ingestion.parsing import (
    BoundaryDecision,
    CONTEXT_ELISION,
    GatewayTopicSegmenter,
    HeadingTopicSegmenter,
    SegmentationFailure,
    context_window,
    split_into_highlights,
)

TWO_TOPIC_DOCUMENT = """# Photosynthesis

Photosynthesis converts light energy into chemical energy in plants. \
Chlorophyll absorbs light energy. Chloroplasts contain chlorophyll. During \
photosynthesis, plants use carbon dioxide and water to produce glucose and \
oxygen. Glucose stores chemical energy. Plants release oxygen into the \
atmosphere.

# Respiration

Respiration releases the energy stored in glucose. Mitochondria carry out \
respiration in the cell. The process consumes oxygen and produces carbon \
dioxide. Aerobic respiration yields far more energy than anaerobic \
respiration does in most organisms studied.
"""


class SuffixSegmenter:
    """Returns a fixed second topic, whatever the block is."""

    def __init__(self, second: str) -> None:
        self.second = second
        self.calls: list[str] = []

    def second_topic(self, block: str) -> str:
        self.calls.append(block)
        return self.second if block != self.second else ""


class FailingSegmenter:
    def second_topic(self, block: str) -> str:
        raise RuntimeError("segmenter unreachable")


class FakeChatClient:
    def __init__(
        self,
        response: dict | list[dict],
        *,
        resolved_provider: str = "phi4-local",
        resolved_model: str = "phi4:14b-q4_K_M",
    ) -> None:
        self.response = response
        self.resolved_provider = resolved_provider
        self.resolved_model = resolved_model
        self.calls: list[dict] = []
        self.resolution_calls: list[str] = []

    def chat(self, prompt=None, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response

    def resolve_chat_profile(self, profile):
        self.resolution_calls.append(profile)
        return {
            "profile": profile,
            "provider": self.resolved_provider,
            "model": self.resolved_model,
        }


class OneTopicSegmenter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def boundary_decision(self, block: str) -> BoundaryDecision:
        self.calls.append(block)
        return BoundaryDecision(False, None, provider="test", model="test")


def test_every_highlight_is_a_verbatim_slice_of_the_document() -> None:
    # The load-bearing property: evidence quotes are later checked against
    # `text`, and the content store records `start:end` as the real location.
    # Both are wrong the moment a highlight stops being an exact slice.
    highlights = split_into_highlights(
        TWO_TOPIC_DOCUMENT, segmenter=HeadingTopicSegmenter()
    )

    assert len(highlights) == 2
    for highlight in highlights:
        assert (
            TWO_TOPIC_DOCUMENT[highlight.start_char : highlight.end_char]
            == highlight.text
        )
    assert [highlight.index for highlight in highlights] == [0, 1]
    assert [highlight.heading for highlight in highlights] == [
        "Photosynthesis",
        "Respiration",
    ]


def test_context_is_taken_from_both_sides_and_marks_the_removed_highlight() -> None:
    highlights = split_into_highlights(
        TWO_TOPIC_DOCUMENT, segmenter=HeadingTopicSegmenter()
    )
    first, second = highlights

    # The first highlight has nothing before it and the second nothing after,
    # so the elision marker is what says which side the context sits on.
    assert first.context_text is not None
    assert first.context_text.startswith(CONTEXT_ELISION)
    assert "Respiration releases the energy stored in glucose." in first.context_text
    assert second.context_text is not None
    assert second.context_text.endswith(CONTEXT_ELISION)
    assert "Plants release oxygen into the atmosphere." in second.context_text


def test_context_window_takes_a_bounded_number_of_sentences_each_side() -> None:
    document = "A one. B two. C three. D four. TARGET. E five. F six. G seven. H eight."
    start = document.index("TARGET.")
    end = start + len("TARGET.")

    context = context_window(document, start, end, sentences=2)

    assert context == f"C three. D four. {CONTEXT_ELISION} E five. F six."
    assert "B two." not in context
    assert "G seven." not in context


def test_context_is_none_when_the_highlight_is_the_whole_document() -> None:
    document = "Only one sentence here."

    assert context_window(document, 0, len(document)) is None


def test_a_verbatim_suffix_rolls_over_into_the_next_highlight() -> None:
    document = (
        "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu "
        "xi omicron pi rho sigma tau upsilon phi chi psi omega one two three "
        "four five six seven eight nine ten eleven twelve thirteen fourteen. "
        "SECOND TOPIC STARTS HERE and continues to the end of the document."
    )
    second = "SECOND TOPIC STARTS HERE and continues to the end of the document."
    segmenter = SuffixSegmenter(second)

    highlights = split_into_highlights(document, segmenter=segmenter)

    assert len(highlights) == 2
    assert highlights[0].segmentation["outcome"] == "semantic_boundary"
    assert highlights[1].text == second
    assert document[highlights[1].start_char : highlights[1].end_char] == second


def test_a_non_verbatim_boundary_fails_the_document() -> None:
    document = " ".join(f"word{n}" for n in range(60)) + ". Real trailing sentence."
    segmenter = SuffixSegmenter("A suffix the document never actually contained.")

    with pytest.raises(SegmentationFailure) as failure:
        split_into_highlights(document, segmenter=segmenter)

    assert failure.value.code == "non_verbatim_anchor"


def test_an_ambiguous_boundary_anchor_fails_the_document() -> None:
    document = (
        "First sentence. Repeat starts now. "
        + " ".join(f"filler{index}" for index in range(45))
        + ". Repeat starts now."
    )
    segmenter = SuffixSegmenter("Repeat starts now.")

    with pytest.raises(SegmentationFailure) as failure:
        split_into_highlights(document, segmenter=segmenter)

    assert failure.value.code == "ambiguous_anchor"


def test_a_failed_segmenter_fails_fast() -> None:
    document = " ".join(f"word{n}" for n in range(60)) + "."

    with pytest.raises(SegmentationFailure) as failure:
        split_into_highlights(document, segmenter=FailingSegmenter())

    assert failure.value.code == "segmenter_exception"
    assert len(failure.value.attempts) == 1
    assert "RuntimeError" in failure.value.attempts[0]["error"]


@pytest.mark.parametrize("word_count", [1, 39, 40])
def test_short_documents_pass_through_without_a_model_call(word_count: int) -> None:
    segmenter = SuffixSegmenter("anything")
    document = " ".join(f"word{index}" for index in range(word_count))

    highlights = split_into_highlights(document, segmenter=segmenter)

    assert segmenter.calls == []
    assert len(highlights) == 1
    assert highlights[0].text == document
    assert highlights[0].segmentation["outcome"] == "short_document_passthrough"
    assert highlights[0].segmentation["document_words"] == word_count


def test_an_empty_document_produces_no_highlights() -> None:
    assert split_into_highlights("   \n\n  ", segmenter=HeadingTopicSegmenter()) == []


def test_inspection_windows_do_not_split_a_same_topic_document() -> None:
    document = " ".join(f"word{n}" for n in range(250)) + "."
    segmenter = OneTopicSegmenter()

    highlights = split_into_highlights(
        document,
        segmenter=segmenter,
        config=SegmentationConfig(inspection_target_words=100),
    )

    assert len(highlights) == 1
    assert highlights[0].text == document
    assert len(segmenter.calls) == 3
    assert len(highlights[0].segmentation["windows"]) == 3
    assert highlights[0].segmentation["windows"][0]["provider"] == "test"
    assert highlights[0].segmentation["windows"][0]["model"] == "test"


def test_a_long_real_note_shape_has_no_fabricated_window_boundaries() -> None:
    paragraphs = [
        f"Working note {index} keeps discussing the same research question. "
        "The examples and follow-up details remain supporting evidence."
        for index in range(120)
    ]
    document = "\n\n".join(paragraphs)
    segmenter = OneTopicSegmenter()

    highlights = split_into_highlights(
        document,
        segmenter=segmenter,
        config=SegmentationConfig(inspection_target_words=200),
    )

    assert len(highlights) == 1
    assert highlights[0].text == document
    assert len(segmenter.calls) > 3
    assert all(
        window["has_second_topic"] is False
        for window in highlights[0].segmentation["windows"]
    )


def test_a_41_word_document_uses_the_semantic_segmenter() -> None:
    segmenter = OneTopicSegmenter()
    document = " ".join(f"word{index}" for index in range(41))

    highlights = split_into_highlights(document, segmenter=segmenter)

    assert len(segmenter.calls) == 1
    assert highlights[0].text == document


def test_gateway_segmenter_asks_for_a_profile_and_never_names_a_provider() -> None:
    client = FakeChatClient(
        {
            "text": '{"has_second_topic": false, "boundary_id": null}',
            "parsed": {"has_second_topic": False, "boundary_id": None},
            "stop_reason": "end_turn",
            "provider": "phi4-local",
            "model": "phi4:14b-q4_K_M",
        }
    )

    GatewayTopicSegmenter(
        chat_client=client, config=SegmentationConfig()
    ).second_topic("a block of text")

    call = client.calls[0]
    assert client.resolution_calls == ["document-segmentation-v1"]
    assert call["profile"] == "document-segmentation-v1"
    assert call.get("provider") is None
    assert call["temperature"] == 0.0
    assert call["max_tokens"] == 256
    assert call["response_format"]["schema"]["required"] == [
        "has_second_topic",
        "boundary_id",
    ]
    assert "a block of text" in call["prompt"]


def test_gateway_selects_only_a_parser_offered_boundary_id() -> None:
    document = (
        "AI supports the first topic. AI appears again in its evidence. "
        "A genuinely different topic starts here and continues in detail. "
        + " ".join(f"support{index}" for index in range(35))
        + "."
    )
    client = FakeChatClient(
        [
            {
                "parsed": {"has_second_topic": True, "boundary_id": 2},
                "stop_reason": "end_turn",
                "provider": "phi4-local",
                "model": "phi4:14b-q4_K_M",
            },
            {
                "parsed": {"has_second_topic": False, "boundary_id": None},
                "stop_reason": "end_turn",
                "provider": "phi4-local",
                "model": "phi4:14b-q4_K_M",
            },
        ]
    )

    highlights = split_into_highlights(
        document,
        segmenter=GatewayTopicSegmenter(
            chat_client=client, config=SegmentationConfig()
        ),
    )

    assert len(highlights) == 2
    assert highlights[1].text.startswith("A genuinely different topic")
    schema = client.calls[0]["response_format"]["schema"]
    assert schema["properties"]["boundary_id"]["enum"] == [1, 2, 3, None]
    assert '1: "AI appears again' in client.calls[0]["prompt"]


def test_gateway_rejects_a_boundary_id_the_parser_did_not_offer() -> None:
    client = FakeChatClient(
        {
            "parsed": {"has_second_topic": True, "boundary_id": 99},
            "stop_reason": "end_turn",
            "provider": "phi4-local",
            "model": "phi4:14b-q4_K_M",
        }
    )
    document = "First topic ends here. " + " ".join(
        f"word{index}" for index in range(45)
    )

    with pytest.raises(SegmentationFailure) as failure:
        split_into_highlights(
            document,
            segmenter=GatewayTopicSegmenter(
                chat_client=client, config=SegmentationConfig()
            ),
        )

    assert failure.value.code == "invalid_boundary_id"


def test_gateway_segmenter_fails_loud_on_a_truncated_response() -> None:
    # A partial decision must not be mistaken for a valid no-boundary answer.
    client = FakeChatClient(
        {
            "text": '{"has_second_topic":',
            "stop_reason": "max_tokens",
            "provider": "phi4-local",
            "model": "phi4:14b-q4_K_M",
        }
    )

    with pytest.raises(RuntimeError, match="max_tokens"):
        GatewayTopicSegmenter(
            chat_client=client, config=SegmentationConfig()
        ).second_topic("a block of text")


def test_gateway_segmenter_rejects_sonnet_profile_resolution_before_chat() -> None:
    client = FakeChatClient(
        {},
        resolved_provider="anthropic-sonnet",
        resolved_model="claude-sonnet-4-6",
    )

    with pytest.raises(SegmentationFailure) as failure:
        GatewayTopicSegmenter(
            chat_client=client, config=SegmentationConfig()
        ).boundary_decision("a block of text")

    assert failure.value.code == "profile_route_mismatch"
    assert client.calls == []


def test_user_selection_bypasses_segmentation_and_retains_context() -> None:
    segmenter = FailingSegmenter()
    selection = "duration"
    context = "Bond duration measures sensitivity."

    highlights = split_into_highlights(
        selection,
        segmenter=segmenter,
        boundary_origin="user_selection",
        supplied_context_text=context,
        parent_start_char=10,
        parent_end_char=18,
        containing_sentence=context,
    )

    assert len(highlights) == 1
    assert highlights[0].text == selection
    assert highlights[0].context_text == context
    assert highlights[0].segmentation["boundary_origin"] == "user_selection"


def test_multiple_user_selections_become_exact_sibling_highlights() -> None:
    document = "page_scanner_id: 42\n\nFirst passage.\n\nSecond passage.\n"
    first_start = document.index("First")
    second_start = document.index("Second")

    highlights = split_into_highlights(
        document,
        segmenter=FailingSegmenter(),
        boundary_origin="user_selection",
        supplied_selections=[
            {
                "source_start_char": first_start,
                "source_end_char": first_start + len("First passage."),
                "parent_source_ref": "book.md",
                "parent_start_char": 100,
                "parent_end_char": 114,
            },
            {
                "source_start_char": second_start,
                "source_end_char": second_start + len("Second passage."),
                "parent_source_ref": "book.md",
                "parent_start_char": 200,
                "parent_end_char": 215,
            },
        ],
    )

    assert [highlight.text for highlight in highlights] == [
        "First passage.",
        "Second passage.",
    ]
    assert [highlight.index for highlight in highlights] == [0, 1]
    assert [
        highlight.segmentation["parent_start_char"] for highlight in highlights
    ] == [100, 200]
