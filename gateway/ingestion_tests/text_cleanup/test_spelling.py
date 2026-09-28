from __future__ import annotations

from typing import Any

import pytest

from gateway.ingestion.text_cleanup.models import Passage
from gateway.ingestion.text_cleanup.spelling import SpellingUnavailable, request_spelling_proposals

PROFILE = "spelling-review-v1"


class FakeChatClient:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        prompt: str | None = None,
        *,
        system: Any = None,
        profile: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        response_format: Any = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "profile": profile,
                "provider": provider,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def edits_response(edits: list[dict[str, Any]]) -> dict[str, Any]:
    return {"parsed": {"edits": edits}}


def test_gateway_request_is_local_profile_fresh_context_temperature_zero() -> None:
    client = FakeChatClient(edits_response([]))
    request_spelling_proposals(
        [Passage(index=0, text="hello world")],
        chat_client=client,
        profile=PROFILE,
    )
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["profile"] == PROFILE
    assert call["provider"] is None
    assert call["temperature"] == 0
    assert call["system"] is not None
    assert call["response_format"]["type"] == "json_schema"


def test_valid_output_carries_exact_location_original_suggested() -> None:
    client = FakeChatClient(
        edits_response([{"line": 1, "original": "recieve", "suggested": "receive"}])
    )
    candidates = request_spelling_proposals(
        [Passage(index=0, text="I will recieve the package.")],
        chat_client=client,
        profile=PROFILE,
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.original_text == "recieve"
    assert candidate.proposed_text == "receive"
    assert candidate.phase == "spelling"
    assert candidate.proposal_source == f"model:{PROFILE}"


def test_out_of_order_model_edits_receive_document_order_ids_and_ordinals() -> None:
    client = FakeChatClient(
        edits_response(
            [
                {"line": 2, "original": "adress", "suggested": "address"},
                {"line": 1, "original": "recieve", "suggested": "receive"},
            ]
        )
    )
    candidates = request_spelling_proposals(
        [Passage(index=0, text="recieve it\nadress it")],
        chat_client=client,
        profile=PROFILE,
    )
    assert [item.original_text for item in candidates] == ["recieve", "adress"]
    assert [item.ordinal for item in candidates] == [1, 2]
    assert [item.occurrence_id.rsplit("-", 1)[-1] for item in candidates] == ["1", "2"]


def test_missing_structured_output_is_unavailable_not_no_suggestions() -> None:
    client = FakeChatClient({"text": "not json"})
    with pytest.raises(SpellingUnavailable):
        request_spelling_proposals(
            [Passage(index=0, text="hello world")], chat_client=client, profile=PROFILE
        )


def test_missing_edits_key_is_unavailable() -> None:
    client = FakeChatClient({"parsed": {"nope": []}})
    with pytest.raises(SpellingUnavailable):
        request_spelling_proposals(
            [Passage(index=0, text="hello world")], chat_client=client, profile=PROFILE
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"edits": [{"line": "one", "original": "recieve", "suggested": "receive"}]},
        {"edits": [{"line": 1, "original": 3, "suggested": "three"}]},
        {"edits": ["not-an-edit"]},
        {"edits": [], "unexpected": True},
    ],
)
def test_wrong_edit_schema_is_unavailable_not_no_suggestions(
    payload: dict[str, Any],
) -> None:
    client = FakeChatClient({"parsed": payload})
    with pytest.raises(SpellingUnavailable):
        request_spelling_proposals(
            [Passage(index=0, text="I will recieve the package.")],
            chat_client=client,
            profile=PROFILE,
        )


def test_gateway_exception_is_unavailable() -> None:
    client = FakeChatClient(RuntimeError("boom"))
    with pytest.raises(SpellingUnavailable):
        request_spelling_proposals(
            [Passage(index=0, text="hello world")], chat_client=client, profile=PROFILE
        )


def test_wrong_line_is_rejected() -> None:
    client = FakeChatClient(edits_response([{"line": 99, "original": "recieve", "suggested": "receive"}]))
    candidates = request_spelling_proposals(
        [Passage(index=0, text="I will recieve the package.")], chat_client=client, profile=PROFILE
    )
    assert candidates == []


def test_wrong_original_at_claimed_line_is_rejected() -> None:
    client = FakeChatClient(edits_response([{"line": 1, "original": "banana", "suggested": "banna"}]))
    candidates = request_spelling_proposals(
        [Passage(index=0, text="I will recieve the package.")], chat_client=client, profile=PROFILE
    )
    assert candidates == []


@pytest.mark.parametrize(
    "original,suggested",
    [
        ("hello there", "hi there"),  # multi-word original
        ("hello", "hi there"),  # multi-word suggestion
    ],
)
def test_multi_word_proposals_are_rejected(original: str, suggested: str) -> None:
    client = FakeChatClient(edits_response([{"line": 1, "original": original, "suggested": suggested}]))
    candidates = request_spelling_proposals(
        [Passage(index=0, text=f"{original} world")], chat_client=client, profile=PROFILE
    )
    assert candidates == []


def test_casing_only_difference_is_rejected() -> None:
    client = FakeChatClient(edits_response([{"line": 1, "original": "Hello", "suggested": "hello"}]))
    candidates = request_spelling_proposals(
        [Passage(index=0, text="Hello world")], chat_client=client, profile=PROFILE
    )
    assert candidates == []


def test_over_distance_proposal_is_rejected() -> None:
    client = FakeChatClient(edits_response([{"line": 1, "original": "cat", "suggested": "elephant"}]))
    candidates = request_spelling_proposals(
        [Passage(index=0, text="cat sat")], chat_client=client, profile=PROFILE
    )
    assert candidates == []


def test_all_capital_proposal_is_rejected() -> None:
    client = FakeChatClient(edits_response([{"line": 1, "original": "NASA", "suggested": "NASE"}]))
    candidates = request_spelling_proposals(
        [Passage(index=0, text="NASA launched")], chat_client=client, profile=PROFILE
    )
    assert candidates == []


def test_two_or_fewer_letter_proposal_is_rejected() -> None:
    client = FakeChatClient(edits_response([{"line": 1, "original": "hi", "suggested": "ho"}]))
    candidates = request_spelling_proposals(
        [Passage(index=0, text="hi there")], chat_client=client, profile=PROFILE
    )
    assert candidates == []


def test_protected_region_proposal_is_rejected() -> None:
    client = FakeChatClient(edits_response([{"line": 1, "original": "recieve", "suggested": "receive"}]))
    candidates = request_spelling_proposals(
        [Passage(index=0, text="See `recieve` in code.")], chat_client=client, profile=PROFILE
    )
    assert candidates == []


def test_accept_and_reject_recompute_via_shared_model_functions() -> None:
    from gateway.ingestion.text_cleanup.models import recompute_passages

    client = FakeChatClient(edits_response([{"line": 1, "original": "recieve", "suggested": "receive"}]))
    passages = [Passage(index=0, text="I will recieve the package.")]
    candidates = request_spelling_proposals(passages, chat_client=client, profile=PROFILE)
    occurrence_id = candidates[0].occurrence_id

    accepted = recompute_passages(passages, candidates, {occurrence_id: "accept"})
    assert accepted[0].text == "I will receive the package."

    rejected = recompute_passages(passages, candidates, {occurrence_id: "reject"})
    assert rejected[0].text == passages[0].text
