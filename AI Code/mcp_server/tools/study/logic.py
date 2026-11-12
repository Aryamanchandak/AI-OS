"""
study/logic.py
---------------
MCP tools: study-system spaced-repetition engine (flashcards, FSRS review,
Feynman/challenger practice, temporary overrides).

Backed by study_system.core.study_core.StudyCore via this group's own
adapter.py (study-system no longer has an mcp/ package — this repo is the
sole MCP surface as of 2026-07-18; see
Learning System/plans/09_MCP_ADAPTER_RELOCATION.md).
See Learning System/plans/02_STUDY_AUTOMATION_MCP_AND_CONFIG.md.

study_evaluate_feynman / study_grade_challenger grade through the shared LLM
gateway (StudyCore's configured practice_evaluator) and persist the result
directly — the response contains an "evaluation" key and an "outcome_id",
and no further call is needed. study_record_feynman_evaluation /
study_record_challenger_evaluation are a fallback only: if the gateway is
unavailable, evaluate/grade instead return a "grading_prompt" key (no
"evaluation" key) for the calling agent to reason over itself in that case,
and only then should the agent report its own structured evaluation back via
the matching record_* tool.
"""
from __future__ import annotations

from typing import Any

from .adapter import StudyMCPTools, build_mcp_core

_tools: StudyMCPTools | None = None


def _get_tools() -> StudyMCPTools:
    """Lazily build the StudyCore on first use, not at server import time.

    Matches the pattern in vector_db/search/logic.py and
    knowledge_graph/graph/logic.py: a broken backend (missing baseline.json,
    unresolvable Database root, bad DB path) should only fail this group's
    calls, not take down the whole shared MCP server at startup.
    """
    global _tools
    if _tools is None:
        _tools = StudyMCPTools(build_mcp_core())
    return _tools


def study_generate_cards(
    temporary_count: int | None = None, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Generate flashcards now for unseen/underrepresented concepts."""
    return _get_tools().generate_cards_now(temporary_count, idempotency_key=idempotency_key)


def study_get_due_cards(limit: int | None = None) -> dict[str, Any]:
    """Return FSRS-due flashcards for review."""
    return _get_tools().fetch_due_cards(limit)


def study_submit_review(
    card_id: str, rating: int, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Submit a review rating (1=Again, 2=Hard, 3=Good, 4=Easy) for one card and update its FSRS state."""
    return _get_tools().submit_card_rating(card_id, rating, idempotency_key=idempotency_key)


def study_start_feynman(
    concept_id: str | None = None, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Begin a Feynman explanation practice attempt; returns an opening prompt.

    Omit concept_id to let study-system auto-select an unseen/underpracticed
    concept. This call is deterministic and read-only — it does not create any
    persisted session state, so it is safe to call again if you're unsure
    whether the first call landed.
    """
    return _get_tools().start_feynman(concept_id, idempotency_key=idempotency_key)


def study_evaluate_feynman(
    attempt_id: str,
    explanation: str,
    conversation_so_far: list[dict[str, str]] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Grade a student's Feynman explanation and persist the outcome.

    Normally grades via the shared LLM gateway and returns {"evaluation": ...,
    "outcome_id": ..., "status": "done"|"continue"} — already persisted, no
    further call needed. Only if the gateway is unavailable does it instead
    return {"grading_prompt": ...} for you to grade yourself and report back
    via study_record_feynman_evaluation.

    study-system holds no session state between turns — pass every prior turn
    of this attempt as conversation_so_far (list of {"role": ..., "content":
    ...} dicts) on each call so grading has full context, not just the latest
    message.
    """
    return _get_tools().evaluate_feynman(
        attempt_id,
        explanation,
        conversation_so_far=conversation_so_far,
        idempotency_key=idempotency_key,
    )


def study_record_feynman_evaluation(attempt_id: str, evaluation: dict[str, Any]) -> dict[str, Any]:
    """Fallback only: persist your own structured Feynman evaluation
    (gaps/shallow_areas/connections_missed/overall_assessment/ready_to_conclude)
    for an attempt. Only needed if study_evaluate_feynman returned a
    grading_prompt instead of an evaluation (gateway was unavailable) — when
    it returns an evaluation directly, it is already persisted and this call
    is unnecessary."""
    return _get_tools().record_feynman_evaluation(attempt_id, evaluation)


def study_start_challenger(
    concept_id: str | None = None, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Begin a Socratic-challenger practice attempt; returns an opening prompt.

    Omit concept_id to let study-system auto-select an unseen/underpracticed
    concept. Deterministic and read-only — no persisted session state.
    """
    return _get_tools().start_challenger(concept_id, idempotency_key=idempotency_key)


def study_grade_challenger(
    attempt_id: str,
    answer: str,
    conversation_so_far: list[dict[str, str]] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Grade a student's challenger answer and persist the outcome.

    Normally grades via the shared LLM gateway and returns {"evaluation": ...,
    "outcome_id": ..., "status": "done"|"continue"} — already persisted, no
    further call needed. Only if the gateway is unavailable does it instead
    return {"grading_prompt": ...} for you to grade yourself and report back
    via study_record_challenger_evaluation.

    Pass every prior turn of this attempt as conversation_so_far (list of
    {"role": ..., "content": ...} dicts) on each call — study-system does not
    retain conversation state between turns.
    """
    return _get_tools().grade_challenger(
        attempt_id,
        answer,
        conversation_so_far=conversation_so_far,
        idempotency_key=idempotency_key,
    )


def study_record_challenger_evaluation(attempt_id: str, evaluation: dict[str, Any]) -> dict[str, Any]:
    """Fallback only: persist your own structured challenger evaluation
    (initial_probe/follow_up_probes/edge_cases/known_traps) for an attempt.
    Only needed if study_grade_challenger returned a grading_prompt instead of
    an evaluation (gateway was unavailable) — when it returns an evaluation
    directly, it is already persisted and this call is unnecessary."""
    return _get_tools().record_challenger_evaluation(attempt_id, evaluation)


def study_progress(recent_limit: int = 20) -> dict[str, Any]:
    """Return study-system progress: cards, final-KG concept coverage, unseen
    concepts, due reviews, generation-run count, recent cross-workflow
    activity (generation/review/practice, most recent first, bounded by
    recent_limit), and currently active temporary overrides."""
    return _get_tools().progress_counts(recent_limit=recent_limit)


def study_set_temporary_override(
    setting: str,
    value: Any,
    starts_on: str,
    expires_on: str,
    reason: str,
    created_by: str = "chat",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Add a bounded, expiring override to a baseline setting (e.g. more daily card sets for two weeks)."""
    return _get_tools().set_temporary_override(
        setting=setting,
        value=value,
        starts_on=starts_on,
        expires_on=expires_on,
        reason=reason,
        created_by=created_by,
        idempotency_key=idempotency_key,
    )


def study_cancel_temporary_override(
    override_id: str, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Revoke an active temporary override before its expiry."""
    return _get_tools().cancel_temporary_override(override_id, idempotency_key=idempotency_key)
