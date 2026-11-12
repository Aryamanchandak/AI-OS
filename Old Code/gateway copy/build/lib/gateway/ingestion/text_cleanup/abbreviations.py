"""Abbreviation candidate discovery: literal matching, never regex.

Matching is escaped-literal text search per mapping, boundary-checked so
`dur` cannot match inside `duration` while punctuation-bearing shorthand like
`w/` still matches (component_8.md section 6.2).
"""

from __future__ import annotations

from dataclasses import dataclass

from gateway.ingestion.text_cleanup.models import Candidate, Passage
from gateway.ingestion.text_cleanup.protected import find_protected_spans, intersects


@dataclass(frozen=True)
class MappingRow:
    id: str
    shorthand: str
    expansion: str
    case_sensitive: bool


def _boundary_ok(text: str, start: int, end: int, shorthand: str) -> bool:
    """Boundary depends only on whether the shorthand's own first/last
    character is alphanumeric -- a punctuation-leading/trailing shorthand
    (like ``w/``) is not required to be flanked by non-alphanumerics on that
    side, since it already cannot be embedded in a larger word there."""

    if shorthand[0].isalnum() and start > 0 and text[start - 1].isalnum():
        return False
    if shorthand[-1].isalnum() and end < len(text) and text[end].isalnum():
        return False
    return True


def _fold_preserving_length(value: str) -> str:
    """Lowercase ``value`` without changing its character count.

    ``str.lower()`` is not length-preserving: ``"\u0130".lower()`` is two
    characters, so a single Turkish dotted capital I slides every later index
    of the lowered haystack one place out of step with the original text.
    Matches then land on the wrong offsets and the reviewer is shown -- and
    can apply -- a replacement over the wrong characters. Folding one
    character at a time and keeping only its first lowered character keeps
    the two strings aligned index for index.
    """

    return "".join((character.lower() or character)[0] for character in value)


def _find_literal(text: str, shorthand: str, case_sensitive: bool) -> list[tuple[int, int]]:
    if not shorthand:
        return []
    haystack = text if case_sensitive else _fold_preserving_length(text)
    needle = shorthand if case_sensitive else _fold_preserving_length(shorthand)
    matches: list[tuple[int, int]] = []
    cursor = 0
    while True:
        index = haystack.find(needle, cursor)
        if index == -1:
            break
        end = index + len(shorthand)
        if _boundary_ok(text, index, end, shorthand):
            matches.append((index, end))
        cursor = index + 1
    return matches


def find_candidates(
    passages: list[Passage], mappings: list[MappingRow]
) -> list[Candidate]:
    """Compute abbreviation candidates in document order.

    Matches from different mappings are non-overlapping: the earliest-starting
    match at a position wins and later overlapping matches are discarded,
    keeping the result deterministic regardless of mapping list order.
    """

    candidates: list[Candidate] = []
    ordinal = 0
    for passage in passages:
        protected = find_protected_spans(passage.text)
        raw: list[tuple[int, int, MappingRow]] = []
        for mapping in mappings:
            for start, end in _find_literal(passage.text, mapping.shorthand, mapping.case_sensitive):
                if not intersects(protected, start, end):
                    raw.append((start, end, mapping))
        raw.sort(
            key=lambda item: (
                item[0],
                -(item[1] - item[0]),
                item[2].shorthand,
                item[2].case_sensitive,
                item[2].id,
            )
        )

        claimed_end = -1
        for start, end, mapping in raw:
            if start < claimed_end:
                continue
            claimed_end = end
            ordinal += 1
            candidates.append(
                Candidate(
                    occurrence_id=f"abbr-p{passage.index if passage.index is not None else 0}-{start}-{end}-{ordinal}",
                    phase="abbreviation",
                    passage_index=passage.index,
                    ordinal=ordinal,
                    base_start=start,
                    base_end=end,
                    original_text=passage.text[start:end],
                    proposed_text=mapping.expansion,
                    mapping_id=mapping.id,
                    proposal_source=f"mapping:{mapping.id}",
                )
            )
    return candidates
