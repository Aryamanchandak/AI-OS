import pytest

from s13proof.core_scenarios.scenarios import live_procurement_prompt, memory_correction_prompt, semantic_document_prompt


@pytest.mark.asyncio
async def test_live_prompt_grows_after_real_market_outcome():
    proof = await live_procurement_prompt()
    assert proof["first_frontier"] == ["budget", "market"]
    assert proof["conditional_expansion"] == ["legal"]
    assert proof["executed"] == ["budget", "market", "legal"]
    assert "approved" in proof["final_answer"]


def test_user_correction_changes_the_real_answer_not_just_the_index():
    proof = memory_correction_prompt()
    assert proof["answer"] == "Laptop budget is ₹75,000."
    assert proof["evidence"] == "chat://travel/2"
    assert proof["old_status"] == "superseded"


def test_semantic_prompt_returns_an_answerable_piece_of_evidence():
    proof = semantic_document_prompt()
    evidence = " ".join(proof["semantic_answer_evidence"].split())
    assert "second Gemini key supplies separate quota" in evidence
    assert not any("second Gemini key supplies separate quota" in " ".join(window.split())
                   for window in proof["fixed_windows"])
