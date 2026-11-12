"""Stateless MCP adapter over study-system's StudyCore.

Moved here 2026-07-18 from study_system/mcp/tools.py — this repo's shared
`study` tool group is now the sole MCP surface for study-system (see
Learning System/plans/08_MCP_SURFACE_RECONCILIATION.md and
plans/09_MCP_ADAPTER_RELOCATION.md). study-system no longer has an mcp/
package; it owns only the domain logic (core/, automation/, repositories/,
storage/, scheduling/, types/) that this module builds a StudyCore from.

Ported verbatim (no behavior changes) except for the import paths above.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
import uuid

from study_system.core.baseline import BASELINE_PATH, load_baseline
from study_system.core.study_core import StructuralQualityChecker, StudyCore, TemplateCardGenerator
from study_system.core.gateway import (
    GatewayCardGenerator,
    GatewayPracticeEvaluator,
    GatewayQualityChecker,
    LLMGateway,
)
from study_system.repositories.json_repositories import (
    EmptyKGRepository,
    JsonKGRepository,
    JsonVectorRepository,
)
from study_system.storage.mvp_store import MVPStore


def build_mcp_core(baseline_path: Path = BASELINE_PATH) -> StudyCore:
    """Build a StudyCore for interactive MCP use.

    Unlike automation.generate.build_core, this does not require a
    kg_concepts_path to be configured — due-card review, ratings, overrides,
    and progress all work without a KG source. Anything that actually needs
    concept lookups (generation, Feynman, challenger) will raise a clear
    KeyError/RuntimeError at call time instead of at server startup.
    """

    baseline = load_baseline(baseline_path)
    store = MVPStore(baseline.sqlite_path)
    kg = JsonKGRepository(baseline.kg_concepts_path) if baseline.kg_concepts_path else EmptyKGRepository()
    vector = JsonVectorRepository(baseline.vector_snippets_path)
    gateway = LLMGateway(baseline.llm_gateway_url, baseline.gateway_timeout_seconds)
    generator = (
        GatewayCardGenerator(gateway)
        if baseline.generation_backend == "gateway"
        else TemplateCardGenerator()
    )
    quality = (
        GatewayQualityChecker(gateway)
        if baseline.generation_backend == "gateway" and baseline.quality_backend == "gateway"
        else StructuralQualityChecker()
    )
    return StudyCore(
        baseline=baseline,
        store=store,
        kg=kg,
        vector=vector,
        generator=generator,
        quality=quality,
        practice_evaluator=GatewayPracticeEvaluator(gateway),
    )


def _write_key(value: str | None) -> str:
    return value or str(uuid.uuid4())


def _with_key(result: dict[str, Any], key: str) -> dict[str, Any]:
    return {**result, "idempotency_key": key}


class StudyMCPTools:
    def __init__(self, core: StudyCore) -> None:
        self._core = core

    def generate_cards_now(
        self, temporary_count: int | None = None, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        key = _write_key(idempotency_key)
        return _with_key(
            self._core.generate_unseen_cards(temporary_count=temporary_count, idempotency_key=key),
            key,
        )

    def fetch_due_cards(
        self, limit: int | None = None, *, card_types: tuple[str, ...] | None = ("flashcard",)
    ) -> dict[str, Any]:
        cards = self._core.fetch_due_cards(limit=limit, card_types=card_types)
        return {"cards": cards, "count": len(cards)}

    def submit_card_rating(
        self, card_id: str, rating: int, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        key = _write_key(idempotency_key)
        return _with_key(self._core.submit_card_rating(card_id, rating, idempotency_key=key), key)

    def start_feynman(
        self, concept_id: str | None = None, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        key = _write_key(idempotency_key)
        return _with_key(self._core.start_feynman(concept_id, idempotency_key=key), key)

    def evaluate_feynman(
        self,
        attempt_id: str,
        explanation: str,
        *,
        conversation_so_far: list[dict[str, str]] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        key = _write_key(idempotency_key)
        return _with_key(
            self._core.evaluate_feynman(
                attempt_id,
                explanation,
                conversation_so_far=conversation_so_far,
                idempotency_key=key,
            ),
            key,
        )

    def record_feynman_evaluation(self, attempt_id: str, evaluation: dict[str, Any]) -> dict[str, Any]:
        return self._core.record_feynman_evaluation(attempt_id, evaluation)

    def start_challenger(
        self, concept_id: str | None = None, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        key = _write_key(idempotency_key)
        return _with_key(self._core.start_challenger(concept_id, idempotency_key=key), key)

    def grade_challenger(
        self,
        attempt_id: str,
        answer: str,
        *,
        conversation_so_far: list[dict[str, str]] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        key = _write_key(idempotency_key)
        return _with_key(
            self._core.grade_challenger(
                attempt_id,
                answer,
                conversation_so_far=conversation_so_far,
                idempotency_key=key,
            ), key
        )

    def record_challenger_evaluation(self, attempt_id: str, evaluation: dict[str, Any]) -> dict[str, Any]:
        return self._core.record_challenger_evaluation(attempt_id, evaluation)

    def progress_counts(self, *, recent_limit: int = 20) -> dict[str, Any]:
        return self._core.progress_counts(recent_limit=recent_limit)

    def set_temporary_override(
        self,
        *,
        setting: str,
        value: Any,
        starts_on: str,
        expires_on: str,
        reason: str,
        created_by: str = "agent",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        key = _write_key(idempotency_key)
        return _with_key(
            self._core.set_temporary_override(
                setting=setting,
                value=value,
                starts_on=date.fromisoformat(starts_on),
                expires_on=date.fromisoformat(expires_on),
                reason=reason,
                created_by=created_by,
                idempotency_key=key,
            ),
            key,
        )

    def cancel_temporary_override(
        self, override_id: str, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        key = _write_key(idempotency_key)
        return _with_key(
            self._core.cancel_temporary_override(override_id, idempotency_key=key), key
        )
