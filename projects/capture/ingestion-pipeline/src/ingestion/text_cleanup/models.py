"""Shared phase, occurrence, and recomputation types for text cleanup.

Kept phase-agnostic on purpose: abbreviation and spelling both produce
``Candidate`` rows against an immutable base-text snapshot and both recompute
working text the same way, so one recompute implementation serves both
phases (component_8.md section 6.2/6.3 describe the same recompute rule
twice, once per phase).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Phase = Literal["abbreviation", "spelling"]
SourceKind = Literal["image", "text_file", "typed_highlight"]

# Actions that resolve an occurrence (as opposed to navigation, which does not).
RESOLVING_ACTIONS: dict[Phase, tuple[str, ...]] = {
    "abbreviation": ("apply_once", "apply_remember", "skip"),
    "spelling": ("accept", "reject"),
}

# Actions whose effective text is the candidate's proposed_text rather than
# its original_text.
_REPLACING_ACTIONS = frozenset({"apply_once", "apply_remember", "accept"})


@dataclass(frozen=True)
class Passage:
    """One unit of phase text. ``index`` is None only for a single-passage
    text_file source; image sources carry the page-scanner passage index."""

    index: int | None
    text: str


@dataclass(frozen=True)
class Candidate:
    """One detected occurrence, positioned on the phase's immutable base text.

    Stable across recompute: occurrence_id and base_start/base_end never
    change once a phase's candidates are computed (component_8.md section
    6.2: "Stable occurrence IDs derive from phase + passage + base offsets +
    ordinal, not mutable current offsets").
    """

    occurrence_id: str
    phase: Phase
    passage_index: int | None
    ordinal: int
    base_start: int
    base_end: int
    original_text: str
    proposed_text: str
    mapping_id: str | None
    proposal_source: str


def effective_text(candidate: Candidate, action: str | None) -> str:
    return candidate.proposed_text if action in _REPLACING_ACTIONS else candidate.original_text


def recompute_passages(
    base_passages: list[Passage],
    candidates: list[Candidate],
    decisions: dict[str, str],
) -> list[Passage]:
    """Apply decided replacements to a fresh copy of base text.

    Always splices from base_start/base_end on the immutable base text, never
    from a previous working text, so replacements cannot cascade or
    accumulate drift across re-decisions (section 6.2: "Do not mutate a
    replacement repeatedly in place").
    """

    by_passage: dict[int | None, list[Candidate]] = {}
    for candidate in candidates:
        by_passage.setdefault(candidate.passage_index, []).append(candidate)

    result: list[Passage] = []
    for passage in base_passages:
        applicable = sorted(
            by_passage.get(passage.index, []), key=lambda c: c.base_start, reverse=True
        )
        text = passage.text
        for candidate in applicable:
            action = decisions.get(candidate.occurrence_id)
            if action in _REPLACING_ACTIONS:
                text = (
                    text[: candidate.base_start]
                    + candidate.proposed_text
                    + text[candidate.base_end :]
                )
        result.append(Passage(index=passage.index, text=text))
    return result


def current_offsets(
    candidates: list[Candidate], decisions: dict[str, str]
) -> dict[str, tuple[int, int]]:
    """Position of each candidate in the current (recomputed) working text.

    Only earlier (lower base_start), same-passage, decided replacements shift
    a later occurrence's position -- an undecided or skipped/rejected
    occurrence keeps its base length.
    """

    by_passage: dict[int | None, list[Candidate]] = {}
    for candidate in candidates:
        by_passage.setdefault(candidate.passage_index, []).append(candidate)

    offsets: dict[str, tuple[int, int]] = {}
    for group in by_passage.values():
        ordered = sorted(group, key=lambda c: c.base_start)
        delta = 0
        for candidate in ordered:
            action = decisions.get(candidate.occurrence_id)
            text = effective_text(candidate, action)
            start = candidate.base_start + delta
            end = start + len(text)
            offsets[candidate.occurrence_id] = (start, end)
            delta += len(text) - (candidate.base_end - candidate.base_start)
    return offsets
