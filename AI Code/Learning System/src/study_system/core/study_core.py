"""Reusable MVP learning services.

This module contains the learning rules used by both automation and MCP-style
interfaces. It deliberately has no terminal/chat-specific behavior.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from study_system.core.baseline import (
    StudyBaseline,
    effective_config_json,
    merge_overrides,
    validate_override,
)
from study_system.repositories.interfaces import FinalKGRepository, VectorRepository
from study_system.scheduling.scheduler import FSRSScheduler
from study_system.storage.mvp_store import MVPStore
from study_system.types.card import CardRating, FSRSState
from study_system.types.mvp import ConceptSummary, GeneratedCard, RetrievedContext


_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "review" / "prompts"


def _render_prompt(filename: str, **values: str) -> str:
    text = (_PROMPTS_DIR / filename).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _validate_feynman_evaluation(evaluation: dict[str, Any]) -> None:
    required = {"gaps", "shallow_areas", "connections_missed", "overall_assessment", "ready_to_conclude"}
    missing = required - evaluation.keys()
    if missing:
        raise ValueError(f"Feynman evaluation missing required keys: {sorted(missing)}")


def _validate_challenger_evaluation(evaluation: dict[str, Any]) -> None:
    required = {"initial_probe", "follow_up_probes", "edge_cases", "known_traps"}
    missing = required - evaluation.keys()
    if missing:
        raise ValueError(f"Challenger evaluation missing required keys: {sorted(missing)}")


class CardGenerator(Protocol):
    def generate(self, context: RetrievedContext, target_count: int, config: StudyBaseline) -> list[GeneratedCard]:
        """Generate validated cards for one concept."""


class QualityChecker(Protocol):
    def check(
        self, cards: list[GeneratedCard], context: RetrievedContext, config: StudyBaseline
    ) -> list[GeneratedCard]:
        """Return the subset of cards accepted for persistence."""


class PracticeEvaluator(Protocol):
    def evaluate_feynman(self, prompt: str, config: StudyBaseline) -> dict[str, Any]: ...

    def grade_challenger(self, prompt: str, config: StudyBaseline) -> dict[str, Any]: ...


class PassthroughQualityChecker:
    """Accepts every card unchanged.

    Plan 02 §3 requires a "run quality checks" step between generation and
    persistence. The real grounding/rubric logic already exists in
    `validation/quality.py` (legacy, prompt + LLM-gateway based) but wiring it
    here means real API calls with real cost, which is a decision for a
    human, not an autonomous default. This passthrough keeps the pipeline
    shape correct (generate -> check -> persist) so a real checker can be
    swapped in via the `quality=` constructor arg without changing StudyCore.
    """

    def check(
        self, cards: list[GeneratedCard], context: RetrievedContext, config: StudyBaseline
    ) -> list[GeneratedCard]:
        del context, config
        return cards


class StructuralQualityChecker:
    """Deterministic fail-closed checks applied before any card is persisted."""

    def check(
        self, cards: list[GeneratedCard], context: RetrievedContext, config: StudyBaseline
    ) -> list[GeneratedCard]:
        del context
        accepted: list[GeneratedCard] = []
        seen: set[tuple[str, str]] = set()
        for card in cards:
            front = card.front.strip()
            back = card.back.strip()
            identity = (front.casefold(), back.casefold())
            if len(front) < config.quality_min_front_chars:
                continue
            if len(back) < config.quality_min_back_chars:
                continue
            if not card.source_refs:
                continue
            if identity in seen:
                continue
            seen.add(identity)
            accepted.append(card)
        return accepted


class TemplateCardGenerator:
    """Deterministic local generator used for tests and no-network MVP dry runs.

    Production LLM generation can be provided by another CardGenerator
    implementation without changing selectors, storage, automation, or MCP.
    """

    def generate(self, context: RetrievedContext, target_count: int, config: StudyBaseline) -> list[GeneratedCard]:
        cards: list[GeneratedCard] = []
        prompt_version = config.prompt_versions.get("flashcard", "card_generation_flashcard_v1")
        summary = context.concept.summary or f"Key details for {context.concept.name}"
        snippets = [
            str(item.get("text") or item.get("content") or "")
            for item in context.vector_context
            if item.get("text") or item.get("content")
        ]
        source = snippets[0] if snippets else summary
        for idx in range(target_count):
            cards.append(
                GeneratedCard(
                    id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            "study-card:"
                            f"{context.concept.id}:{context.concept.source_version or 'unversioned'}:"
                            f"{prompt_version}:{idx}",
                        )
                    ),
                    concept_id=context.concept.id,
                    front=f"{context.concept.name}: core check {idx + 1}",
                    back=source,
                    card_type="flashcard",
                    source_refs=context.source_refs,
                    source_version=context.concept.source_version,
                    model=config.card_gen_model,
                    prompt_version=prompt_version,
                )
            )
        return cards


class StudyCore:
    def __init__(
        self,
        *,
        baseline: StudyBaseline,
        store: MVPStore,
        kg: FinalKGRepository,
        vector: VectorRepository,
        generator: CardGenerator | None = None,
        scheduler: FSRSScheduler | None = None,
        quality: QualityChecker | None = None,
        practice_evaluator: PracticeEvaluator | None = None,
    ) -> None:
        self._baseline = baseline
        self._store = store
        self._kg = kg
        self._vector = vector
        self._generator = generator or TemplateCardGenerator()
        self._scheduler = scheduler or FSRSScheduler(
            weights=list(baseline.fsrs_weights) or None,
            fuzz_range=(0.95, 1.05),
        )
        self._quality = quality or StructuralQualityChecker()
        self._practice_evaluator = practice_evaluator

    def close(self) -> None:
        self._store.close()

    def effective_config(self, on_date: date | None = None) -> StudyBaseline:
        return merge_overrides(self._baseline, self._store.active_overrides(on_date), today=on_date)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def select_unseen_concepts(self, limit: int | None = None) -> list[ConceptSummary]:
        config = self.effective_config()
        target = limit if limit is not None else config.daily_card_sets
        existing = self._store.concept_ids_with_cards()
        candidates = [
            concept
            for concept in self._kg.list_concepts()
            if concept.id not in existing
        ]
        candidates.sort(key=lambda c: (c.domain, c.name, c.id))
        return candidates[:target]

    def retrieve_context(self, concept: ConceptSummary) -> RetrievedContext:
        kg_context = self._kg.neighborhood(concept.id, depth=1)
        vector_context = self._vector.search(
            f"{concept.name} {concept.summary}",
            filters={"concept_id": concept.id},
            limit=5,
        )
        return RetrievedContext(
            concept=concept,
            kg_context=kg_context,
            vector_context=vector_context,
        )

    def generate_unseen_cards(
        self,
        temporary_count: int | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key:
            cached = self._store.get_idempotent_result(idempotency_key, "generate_unseen_cards")
            if cached is not None:
                return cached

        config = self.effective_config()
        count = temporary_count if temporary_count is not None else config.daily_card_sets
        if count < 1:
            raise ValueError("temporary_count must be >= 1")
        max_count = self._baseline.override_max_values.get("daily_card_sets", 20)
        if count > max_count:
            raise ValueError(f"temporary_count must be <= {max_count}")
        concepts = self.select_unseen_concepts(limit=count)
        selected_ids = [concept.id for concept in concepts]
        run_id = self._store.start_generation_run(
            effective_config_json=effective_config_json(config),
            selected_concept_ids=selected_ids,
        )
        inserted_total = 0
        try:
            for concept in concepts:
                context = self.retrieve_context(concept)
                cards = self._generator.generate(context, config.cards_per_set, config)
                accepted = self._quality.check(cards, context, config)
                inserted_total += self._store.insert_cards(accepted)
            self._store.finish_generation_run(run_id, "success")
            result = {
                "run_id": run_id,
                "selected_concept_ids": selected_ids,
                "cards_inserted": inserted_total,
                "outcome": "success",
                "selection_code": "unseen_coverage",
            }
            if idempotency_key:
                self._store.save_idempotent_result(idempotency_key, "generate_unseen_cards", result)
            return result
        except Exception as exc:
            self._store.finish_generation_run(run_id, "failed", str(exc))
            raise

    # ------------------------------------------------------------------
    # Reviews / FSRS
    # ------------------------------------------------------------------

    def fetch_due_cards(
        self,
        limit: int | None = None,
        *,
        card_types: tuple[str, ...] | None = ("flashcard",),
    ) -> list[dict[str, Any]]:
        effective = self.effective_config()
        requested_limit = limit if limit is not None else effective.review_limit
        if requested_limit < 1 or requested_limit > self._baseline.override_max_values.get("review_limit", 200):
            raise ValueError("limit is outside the configured review bounds")
        rows = self._store.get_due_cards(requested_limit, card_types=card_types)
        cards: list[dict[str, Any]] = []
        for row in rows:
            card = dict(row)
            card["source_refs"] = json.loads(card.pop("source_refs_json") or "[]")
            card["evidence"] = json.loads(card.pop("evidence_json") or "{}")
            cards.append(card)
        return cards

    def submit_card_rating(
        self,
        card_id: str,
        rating: int,
        *,
        now: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key:
            cached = self._store.get_idempotent_result(idempotency_key, "submit_card_rating")
            if cached is not None:
                return cached

        now = now or datetime.utcnow()
        row = self._store.get_card_with_state(card_id)
        if row is None:
            raise KeyError(f"Card not found: {card_id}")

        last_reviewed = (
            datetime.fromisoformat(row["last_reviewed_at"])
            if row["last_reviewed_at"]
            else None
        )
        elapsed_days = (now - last_reviewed).days if last_reviewed else int(row["elapsed_days"] or 0)
        old_state = FSRSState(
            stability=float(row["stability"]),
            difficulty=float(row["difficulty"]),
            elapsed_days=elapsed_days,
            scheduled_days=int(row["scheduled_days"]),
            reps=int(row["reps"]),
            lapses=int(row["lapses"]),
            state=str(row["state"]),
            next_due_at=datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
        )
        new_state = self._scheduler.rate(old_state, CardRating(rating).value, now=now)
        result = {
            "card_id": card_id,
            "rating": int(rating),
            "scheduled_days": new_state.scheduled_days,
            "due_at": new_state.next_due_at.isoformat() if new_state.next_due_at else None,
            "state": new_state.state,
        }
        # Applying the review and recording the idempotency key happen in one
        # commit (MVPStore.apply_review_and_record) so a crash between the two
        # can't leave a rating applied with no cached key, which would let a
        # retry double-apply it.
        self._store.apply_review_and_record(
            card_id,
            new_state,
            reviewed_at=now,
            evidence={
                "last_rating": int(rating),
                "last_reviewed_at": now.isoformat(),
            },
            idempotency_key=idempotency_key,
            idempotent_result=result,
        )
        return result

    # ------------------------------------------------------------------
    # Feynman / challenger
    #
    # The unified chat client owns conversation state. Start calls therefore
    # return a deterministic opaque handle and do not create database rows.
    # Only a completed evaluation is persisted, as a generation_runs-style
    # audit row, preserving the exact four-table MVP schema.
    # ------------------------------------------------------------------

    def _resolve_concept(self, concept_id: str | None) -> ConceptSummary:
        if concept_id:
            concept = self._kg.get_concept(concept_id)
            if concept is None:
                raise KeyError(f"Concept not found: {concept_id}")
            return concept
        concepts = sorted(self._kg.list_concepts(), key=lambda item: (item.domain, item.name, item.id))
        if not concepts:
            raise RuntimeError("No final-KG concepts are available for automatic selection")
        return concepts[0]

    def start_feynman(
        self, concept_id: str | None = None, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        del idempotency_key  # read-only and deterministic; no retry record is needed
        concept = self._resolve_concept(concept_id)
        context = self.retrieve_context(concept)
        return {
            "attempt_id": f"feynman:{concept.id}",
            "concept_id": concept.id,
            "next_prompt": f"Explain {concept.name} in plain language, as if teaching it to a beginner.",
            "source_refs": context.source_refs,
            "status": "continue",
        }

    def _concept_from_attempt(self, attempt_id: str, mode: str) -> ConceptSummary:
        prefix = f"{mode}:"
        if not attempt_id.startswith(prefix) or not attempt_id[len(prefix):]:
            raise ValueError(f"Invalid stateless {mode} attempt handle")
        concept_id = attempt_id[len(prefix):]
        concept = self._kg.get_concept(concept_id)
        if concept is None:
            raise KeyError(f"Concept not found: {concept_id}")
        return concept

    def evaluate_feynman(
        self,
        attempt_id: str,
        explanation: str,
        *,
        conversation_so_far: list[dict[str, str]] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key:
            cached = self._store.get_idempotent_result(idempotency_key, "evaluate_feynman")
            if cached is not None:
                return cached
        if not explanation.strip():
            raise ValueError("explanation cannot be blank")
        concept = self._concept_from_attempt(attempt_id, "feynman")
        vector_hits = self._vector.search(
            f"{concept.name} {concept.summary}", filters={"concept_id": concept.id}, limit=5
        )
        retrieved_facts = "\n".join(
            str(item.get("text") or item.get("content") or "") for item in vector_hits
        )
        atomic_facts = "\n".join(part for part in (concept.summary, retrieved_facts) if part)
        grading_prompt = _render_prompt(
            "feynman_evaluator_v1.md",
            CANONICAL_NAME=concept.name,
            DOMAIN=concept.domain,
            ATOMIC_FACTS=atomic_facts or "(no ground-truth facts retrieved)",
            STUDENT_EXPLANATION=explanation,
        )
        if conversation_so_far:
            grading_prompt += "\n\nConversation history:\n" + json.dumps(
                conversation_so_far, ensure_ascii=False
            )
        result: dict[str, Any] = {
            "attempt_id": attempt_id,
            "concept_id": concept.id,
            "grading_prompt": grading_prompt,
            "status": "continue",
        }
        if self._practice_evaluator is not None:
            evaluation = self._practice_evaluator.evaluate_feynman(grading_prompt, self.effective_config())
            _validate_feynman_evaluation(evaluation)
            context = self.retrieve_context(concept)
            outcome_id = self._store.record_practice_outcome(
                mode="feynman",
                concept_id=concept.id,
                student_input=explanation,
                grading_prompt=grading_prompt,
                evaluation=evaluation,
                source_refs=context.source_refs,
                model=self._baseline.feynman_model,
                prompt_version=self._baseline.prompt_versions.get("feynman", "feynman_evaluator_v1"),
                outcome_id=(
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"study-practice:{idempotency_key}"))
                    if idempotency_key else None
                ),
            )
            result = {
                "attempt_id": attempt_id,
                "outcome_id": outcome_id,
                "concept_id": concept.id,
                "evaluation": evaluation,
                "status": "done" if evaluation["ready_to_conclude"] else "continue",
            }
        if idempotency_key:
            self._store.save_idempotent_result(idempotency_key, "evaluate_feynman", result)
        return result

    def record_feynman_evaluation(self, attempt_id: str, evaluation: dict[str, Any]) -> dict[str, Any]:
        _validate_feynman_evaluation(evaluation)
        concept = self._concept_from_attempt(attempt_id, "feynman")
        context = self.retrieve_context(concept)
        outcome_id = self._store.record_practice_outcome(
            mode="feynman", concept_id=concept.id, student_input="",
            grading_prompt="external evaluation", evaluation=evaluation,
            source_refs=context.source_refs, model=self._baseline.feynman_model,
            prompt_version=self._baseline.prompt_versions.get("feynman", "feynman_evaluator_v1"),
        )
        return {"attempt_id": attempt_id, "outcome_id": outcome_id, "recorded": True}

    def start_challenger(
        self, concept_id: str | None = None, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        del idempotency_key
        concept = self._resolve_concept(concept_id)
        context = self.retrieve_context(concept)
        return {
            "attempt_id": f"challenger:{concept.id}",
            "concept_id": concept.id,
            "next_prompt": f"Make a claim about {concept.name}; I will test edge cases and assumptions.",
            "source_refs": context.source_refs,
            "status": "continue",
        }

    def grade_challenger(
        self,
        attempt_id: str,
        answer: str,
        *,
        conversation_so_far: list[dict[str, str]] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key:
            cached = self._store.get_idempotent_result(idempotency_key, "grade_challenger")
            if cached is not None:
                return cached
        if not answer.strip():
            raise ValueError("answer cannot be blank")
        concept = self._concept_from_attempt(attempt_id, "challenger")
        neighborhood = self._kg.neighborhood(concept.id, depth=1)
        vector_hits = self._vector.search(
            f"{concept.name} {concept.summary}", filters={"concept_id": concept.id}, limit=5
        )
        grading_prompt = _render_prompt(
            "challenger_v1.md",
            CONCEPT_CONTEXT=(
                f"{concept.name} ({concept.domain}): {concept.summary}\n"
                f"KG: {neighborhood}\nVector: {vector_hits}"
            ),
            STUDENT_CLAIM=answer,
        )
        if conversation_so_far:
            grading_prompt += "\n\nConversation history:\n" + json.dumps(
                conversation_so_far, ensure_ascii=False
            )
        result: dict[str, Any] = {
            "attempt_id": attempt_id,
            "concept_id": concept.id,
            "grading_prompt": grading_prompt,
            "status": "continue",
        }
        if self._practice_evaluator is not None:
            evaluation = self._practice_evaluator.grade_challenger(grading_prompt, self.effective_config())
            _validate_challenger_evaluation(evaluation)
            context = self.retrieve_context(concept)
            outcome_id = self._store.record_practice_outcome(
                mode="challenger", concept_id=concept.id, student_input=answer,
                grading_prompt=grading_prompt, evaluation=evaluation,
                source_refs=context.source_refs, model=self._baseline.challenger_model,
                prompt_version=self._baseline.prompt_versions.get("challenger", "challenger_v1"),
                outcome_id=(
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"study-practice:{idempotency_key}"))
                    if idempotency_key else None
                ),
            )
            result = {
                "attempt_id": attempt_id,
                "outcome_id": outcome_id,
                "concept_id": concept.id,
                "evaluation": evaluation,
                "status": "done",
            }
        if idempotency_key:
            self._store.save_idempotent_result(idempotency_key, "grade_challenger", result)
        return result

    def record_challenger_evaluation(self, attempt_id: str, evaluation: dict[str, Any]) -> dict[str, Any]:
        _validate_challenger_evaluation(evaluation)
        concept = self._concept_from_attempt(attempt_id, "challenger")
        context = self.retrieve_context(concept)
        outcome_id = self._store.record_practice_outcome(
            mode="challenger", concept_id=concept.id, student_input="",
            grading_prompt="external evaluation", evaluation=evaluation,
            source_refs=context.source_refs, model=self._baseline.challenger_model,
            prompt_version=self._baseline.prompt_versions.get("challenger", "challenger_v1"),
        )
        return {"attempt_id": attempt_id, "outcome_id": outcome_id, "recorded": True}

    # ------------------------------------------------------------------
    # Progress / overrides
    # ------------------------------------------------------------------

    def progress_counts(self, *, recent_limit: int = 20) -> dict[str, Any]:
        concepts = self._kg.list_concepts()
        covered_ids = self._store.concept_ids_with_cards()
        final_ids = {concept.id for concept in concepts}
        return {
            **self._store.progress_counts(),
            "total_concepts": len(final_ids),
            "unseen_concepts": len(final_ids - covered_ids),
            "recent_activity": self._store.recent_activity(limit=recent_limit),
            "active_overrides": self._store.active_override_records(),
        }

    def set_temporary_override(
        self,
        *,
        setting: str,
        value: Any,
        starts_on: date,
        expires_on: date,
        reason: str,
        created_by: str = "mcp",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key:
            cached = self._store.get_idempotent_result(idempotency_key, "set_temporary_override")
            if cached is not None:
                return cached
        if created_by not in {"user", "agent", "system", "mcp"}:
            raise ValueError("created_by must be user, agent, system, or mcp")
        if not reason.strip():
            raise ValueError("reason cannot be blank")
        value = validate_override(setting, value, self._baseline.override_max_values)
        override_id = self._store.create_override(
            setting=setting,
            value=value,
            starts_on=starts_on,
            expires_on=expires_on,
            reason=reason,
            created_by=created_by,
            override_id=(
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"study-override:{idempotency_key}"))
                if idempotency_key
                else None
            ),
        )
        result = {
            "override_id": override_id,
            "setting": setting,
            "value": value,
            "starts_on": starts_on.isoformat(),
            "expires_on": expires_on.isoformat(),
        }
        if idempotency_key:
            self._store.save_idempotent_result(idempotency_key, "set_temporary_override", result)
        return result

    def cancel_temporary_override(
        self, override_id: str, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        if idempotency_key:
            cached = self._store.get_idempotent_result(idempotency_key, "cancel_temporary_override")
            if cached is not None:
                return cached
        result = {"override_id": override_id, "cancelled": self._store.cancel_override(override_id)}
        if idempotency_key:
            self._store.save_idempotent_result(idempotency_key, "cancel_temporary_override", result)
        return result


def row_to_json(row: Any) -> str:
    return json.dumps(dict(row), sort_keys=True, default=str)
