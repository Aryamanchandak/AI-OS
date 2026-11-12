"""Ephemeral per-item cleanup working state: phase order, navigation, revisions.

Memory-only (component_8.md section 7.2): a run's ``CleanupGate`` owns at
most this run's states, keyed by content hash. Restart discards it; only
mappings and the audit log in :mod:`store` are durable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import re

from .models import (
    Candidate,
    Passage,
    Phase,
    RESOLVING_ACTIONS,
    SourceKind,
    current_offsets,
    effective_text,
    recompute_passages,
)

_CONTEXT_RADIUS = 60
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class IllegalCleanupAction(ValueError):
    pass


@dataclass(frozen=True)
class OccurrenceView:
    candidate: Candidate
    total: int
    current_start: int
    current_end: int
    current_decision: str | None
    sentence: str
    context_before: str
    context_after: str
    before_sentence: str
    after_sentence: str
    # True when self.phase itself has no candidates and this is instead the
    # other (already-settled) phase's last occurrence shown for context --
    # e.g. abbreviation had work, settled, and spelling found nothing. Never
    # re-decidable: decide() always validates against the live self.phase.
    is_fallback_display: bool = False


def _split_sentences(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in _SENTENCE_END.finditer(text):
        spans.append((cursor, match.start()))
        cursor = match.end()
    spans.append((cursor, len(text)))
    return [span for span in spans if span[1] > span[0]] or [(0, len(text))]


def _sentence_neighbors(text: str, start: int) -> tuple[str, str, str]:
    spans = _split_sentences(text)
    index = next((i for i, (s, e) in enumerate(spans) if s <= start < e), len(spans) - 1)
    sentence = text[spans[index][0] : spans[index][1]].strip()
    before = text[spans[index - 1][0] : spans[index - 1][1]].strip() if index > 0 else ""
    after = (
        text[spans[index + 1][0] : spans[index + 1][1]].strip()
        if index < len(spans) - 1
        else ""
    )
    return sentence, before, after


@dataclass
class WorkingState:
    content_hash: str
    source_kind: SourceKind
    abbreviation_base_passages: tuple[Passage, ...]
    abbreviation_candidates: tuple[Candidate, ...]
    abbreviation_decisions: dict[str, str] = field(default_factory=dict)
    phase: Phase = "abbreviation"
    spelling_base_passages: tuple[Passage, ...] | None = None
    spelling_candidates: tuple[Candidate, ...] | None = None
    spelling_decisions: dict[str, str] = field(default_factory=dict)
    current_occurrence_id: str | None = None
    interaction_revision: int = 0
    working_draft_revision: int = 0
    handed_to_final_approval: bool = False
    spelling_unavailable_error: str | None = None

    def __post_init__(self) -> None:
        if self.current_occurrence_id is None and self.abbreviation_candidates:
            self.current_occurrence_id = self.abbreviation_candidates[0].occurrence_id

    def phase_candidates(self, phase: Phase | None = None) -> tuple[Candidate, ...]:
        target = phase or self.phase
        if target == "abbreviation":
            return self.abbreviation_candidates
        return self.spelling_candidates or ()

    def phase_decisions(self, phase: Phase | None = None) -> dict[str, str]:
        target = phase or self.phase
        return self.abbreviation_decisions if target == "abbreviation" else self.spelling_decisions

    def is_phase_settled(self, phase: Phase) -> bool:
        candidates = self.phase_candidates(phase)
        decisions = self.phase_decisions(phase)
        return all(candidate.occurrence_id in decisions for candidate in candidates)

    def spelling_installed(self) -> bool:
        return self.spelling_candidates is not None

    def has_any_cleanup_work(self) -> bool:
        if self.abbreviation_candidates:
            return True
        return bool(self.spelling_candidates)

    def is_fully_resolved(self) -> bool:
        return self.is_phase_settled("abbreviation") and (
            self.spelling_installed() and self.is_phase_settled("spelling")
        )

    def working_passages(self, phase: Phase | None = None) -> list[Passage]:
        target = phase or self.phase
        if target == "abbreviation":
            return recompute_passages(
                list(self.abbreviation_base_passages),
                list(self.abbreviation_candidates),
                self.abbreviation_decisions,
            )
        base = self.spelling_base_passages or ()
        return recompute_passages(
            list(base), list(self.spelling_candidates or ()), self.spelling_decisions
        )

    def current_working_passages(self) -> list[Passage]:
        """The authoritative text right now: settled spelling text once that
        phase has started, otherwise the abbreviation phase's own progress."""

        if self.spelling_installed():
            return self.working_passages("spelling")
        return self.working_passages("abbreviation")

    def install_spelling(self, base_passages: list[Passage], candidates: list[Candidate]) -> None:
        self.spelling_base_passages = tuple(base_passages)
        self.spelling_candidates = tuple(candidates)
        self.phase = "spelling"
        self.spelling_unavailable_error = None
        self.current_occurrence_id = candidates[0].occurrence_id if candidates else None
        # A retry decision re-enters here (component_8.md section 8.5): the
        # shell confirms "retry" the same way as every other cleanup action,
        # by a strictly higher interaction_revision on the same item.
        self.interaction_revision += 1

    def mark_unavailable(self, error: str) -> None:
        self.spelling_unavailable_error = error
        self.interaction_revision += 1

    def clear_unavailable(self) -> None:
        self.spelling_unavailable_error = None

    def mark_handed_off(self) -> None:
        self.handed_to_final_approval = True

    def navigate(self, direction: str) -> None:
        if direction not in ("previous", "next"):
            raise IllegalCleanupAction(f"unsupported navigation direction: {direction!r}")
        candidates = self.phase_candidates()
        if not candidates:
            return
        ids = [candidate.occurrence_id for candidate in candidates]
        index = ids.index(self.current_occurrence_id) if self.current_occurrence_id in ids else 0
        if direction == "next":
            index = min(index + 1, len(ids) - 1)
        else:
            index = max(index - 1, 0)
        self.current_occurrence_id = ids[index]
        self.interaction_revision += 1

    def decision_effect(
        self,
        occurrence_id: str,
        action: str,
        *,
        proposed_text: str | None = None,
    ) -> tuple[Candidate, str, str, bool]:
        """Validate a decision without mutating state.

        The gate uses this before durable audit/mapping writes so a failed
        SQLite transaction can never leave the ephemeral authoritative text
        changed.  The returned boolean says whether the rendered working text
        would actually change; resolving Skip/Reject and repeating an
        identical decision therefore do not advance ``working_draft_revision``.
        """
        candidates = self.phase_candidates()
        candidate = next((c for c in candidates if c.occurrence_id == occurrence_id), None)
        if candidate is None:
            raise IllegalCleanupAction(
                f"occurrence {occurrence_id!r} is not in the current {self.phase} phase"
            )
        if action not in RESOLVING_ACTIONS[self.phase]:
            raise IllegalCleanupAction(
                f"action {action!r} is not legal in the {self.phase} phase"
            )
        candidate_after = (
            replace(candidate, proposed_text=proposed_text)
            if proposed_text is not None
            else candidate
        )
        current_action = self.phase_decisions().get(occurrence_id)
        before_text = effective_text(candidate, current_action)
        after_text = effective_text(candidate_after, action)
        return candidate_after, before_text, after_text, before_text != after_text

    def decide(
        self,
        occurrence_id: str,
        action: str,
        *,
        proposed_text: str | None = None,
    ) -> tuple[str, str]:
        """Commit one already-durable decision to ephemeral working state."""

        candidate, before_text, after_text, text_changed = self.decision_effect(
            occurrence_id, action, proposed_text=proposed_text
        )
        if proposed_text is not None:
            if self.phase == "abbreviation":
                self.abbreviation_candidates = tuple(
                    candidate if item.occurrence_id == occurrence_id else item
                    for item in self.abbreviation_candidates
                )
            else:
                self.spelling_candidates = tuple(
                    candidate if item.occurrence_id == occurrence_id else item
                    for item in (self.spelling_candidates or ())
                )
        decisions = self.phase_decisions()
        decisions[occurrence_id] = action
        self.current_occurrence_id = occurrence_id
        self.interaction_revision += 1
        if text_changed:
            self.working_draft_revision += 1
        return before_text, after_text

    def current_view(self) -> OccurrenceView | None:
        display_phase = self.phase
        candidates = self.phase_candidates(display_phase)
        occurrence_id = self.current_occurrence_id
        is_fallback = False
        if not candidates:
            # This phase has nothing to show (e.g. spelling found zero
            # suggestions). Fall back to the other phase's last occurrence
            # purely for context -- never re-decidable, since decide() only
            # ever validates against the live self.phase, not this display.
            other: Phase = "spelling" if self.phase == "abbreviation" else "abbreviation"
            other_candidates = self.phase_candidates(other)
            if not other_candidates:
                return None
            display_phase = other
            candidates = other_candidates
            occurrence_id = candidates[-1].occurrence_id
            is_fallback = True
        if occurrence_id is None:
            return None
        candidate = next((c for c in candidates if c.occurrence_id == occurrence_id), None)
        if candidate is None:
            return None
        decisions = self.phase_decisions(display_phase)
        offsets = current_offsets(list(candidates), decisions)
        current_start, current_end = offsets[candidate.occurrence_id]
        # Offsets are positions in the *recomputed* working text (earlier
        # decided occurrences may have shifted them), so context must be
        # sliced from that same recomputed passage, not the immutable base.
        working = self.working_passages(display_phase)
        passage_text = next(
            (passage.text for passage in working if passage.index == candidate.passage_index), ""
        )
        context_before = passage_text[max(0, current_start - _CONTEXT_RADIUS) : current_start]
        context_after = passage_text[current_end : current_end + _CONTEXT_RADIUS]
        sentence, before_sentence, after_sentence = _sentence_neighbors(passage_text, current_start)
        return OccurrenceView(
            candidate=candidate,
            total=len(candidates),
            current_start=current_start,
            current_end=current_end,
            current_decision=decisions.get(candidate.occurrence_id),
            sentence=sentence,
            context_before=context_before,
            context_after=context_after,
            before_sentence=before_sentence,
            after_sentence=after_sentence,
            is_fallback_display=is_fallback,
        )
