"""Local-gateway spelling proposals with strict deterministic validation.

The model only nominates line/original/suggested triples; every guard in
component_8.md section 6.3 ("Normal code -- not the model -- must reject a
proposal when...") runs here in Python, never left to model judgment.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ingestion.text_cleanup.models import Candidate, Passage
from ingestion.text_cleanup.protected import find_protected_spans, intersects

EDIT_DISTANCE_THRESHOLD = 3
SPELLING_REQUEST_MAX_CHARS = 120_000

SYSTEM_PROMPT = (
    "You review a line-numbered document for likely single-word spelling "
    "errors only.\n"
    "For each clear misspelling, report its 1-indexed line number, the exact "
    "misspelled word as it appears on that line, and your suggested "
    "correction.\n"
    "NEVER propose a grammar, punctuation, style, paraphrase, or sentence "
    "rewrite. NEVER propose a change that differs only by capitalization. "
    "Only propose single-word corrections, and only when you are confident "
    "it is a spelling error.\n"
    "If you find nothing, return an empty edits list.\n"
    'Respond with exactly one JSON object: {"edits": [{"line": <int>, '
    '"original": <string>, "suggested": <string>}]}. No commentary, no '
    "markdown fences."
)


class ChatClient(Protocol):
    def chat(
        self,
        prompt: str | None = None,
        *,
        system: Any = None,
        provider: str | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        response_format: Any = None,
    ) -> dict[str, Any]: ...


class SpellingUnavailable(RuntimeError):
    """Checker unavailable: malformed JSON, wrong schema, timeout, or gateway
    failure. Never converted to an empty suggestion list (section 6.3)."""


class _SpellingEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line: int = Field(ge=1)
    original: str = Field(min_length=1)
    suggested: str = Field(min_length=1)


class _SpellingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edits: list[_SpellingEdit]


def _document_lines(passages: list[Passage]) -> list[tuple[int | None, str, int]]:
    """Flatten into (passage_index, line_text, offset-within-passage) triples."""

    lines: list[tuple[int | None, str, int]] = []
    for passage in passages:
        cursor = 0
        for line in passage.text.split("\n"):
            lines.append((passage.index, line, cursor))
            cursor += len(line) + 1
    return lines


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, 1):
        current = [index]
        for right_index, right_char in enumerate(right, 1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _is_abbreviation_like(word: str) -> bool:
    letters = [character for character in word if character.isalpha()]
    if len(letters) <= 2:
        return True
    return word.isupper()


def request_spelling_proposals(
    passages: list[Passage],
    *,
    chat_client: ChatClient,
    provider: str,
    model: str | None = None,
) -> list[Candidate]:
    """One fresh, no-history, temperature-0 call for the whole item.

    Raises :class:`SpellingUnavailable` rather than ever returning an empty
    list to mean "the checker failed" -- an empty list means "checked, no
    findings," a different fact.
    """

    lines = _document_lines(passages)
    numbered = "\n".join(f"{index + 1}: {text}" for index, (_, text, _) in enumerate(lines))
    if not numbered.strip():
        return []
    if len(numbered) > SPELLING_REQUEST_MAX_CHARS:
        raise SpellingUnavailable(
            f"spelling input exceeds the {SPELLING_REQUEST_MAX_CHARS}-character request limit"
        )

    try:
        response = chat_client.chat(
            numbered,
            system=SYSTEM_PROMPT,
            provider=provider,
            model=model,
            max_tokens=1536,
            temperature=0,
            response_format={
                "type": "json_schema",
                "name": "spelling_review",
                "schema": _SpellingPayload.model_json_schema(),
            },
        )
    except Exception as error:
        raise SpellingUnavailable(
            f"spelling gateway call failed (provider={provider}, {type(error).__name__}: {error})"
        ) from error

    text = response.get("text") if isinstance(response, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise SpellingUnavailable("spelling gateway returned no text")
    try:
        parsed = _SpellingPayload.model_validate_json(text)
    except ValidationError as error:
        raise SpellingUnavailable(
            f"spelling gateway returned invalid structured output: {error}"
        ) from error

    passage_by_index = {passage.index: passage for passage in passages}
    protected_cache: dict[int | None, list[Any]] = {}
    seen_spans: set[tuple[int | None, int, int]] = set()
    candidates: list[Candidate] = []
    ordinal = 0

    for raw_edit in parsed.edits:
        line_number = raw_edit.line
        original = raw_edit.original
        suggested = raw_edit.suggested
        if not (1 <= line_number <= len(lines)):
            continue
        passage_index, line_text, line_offset = lines[line_number - 1]
        if len(original.split()) != 1 or len(suggested.split()) != 1:
            continue
        if original.lower() == suggested.lower():
            continue
        if _edit_distance(original.lower(), suggested.lower()) > EDIT_DISTANCE_THRESHOLD:
            continue
        if _is_abbreviation_like(original):
            continue
        match = re.search(rf"(?<!\w){re.escape(original)}(?!\w)", line_text)
        if match is None:
            continue
        passage = passage_by_index.get(passage_index)
        if passage is None:
            continue
        start = line_offset + match.start()
        end = line_offset + match.end()
        if passage_index not in protected_cache:
            protected_cache[passage_index] = find_protected_spans(passage.text)
        if intersects(protected_cache[passage_index], start, end):
            continue
        span_key = (passage_index, start, end)
        if span_key in seen_spans:
            continue
        seen_spans.add(span_key)
        ordinal += 1
        candidates.append(
            Candidate(
                occurrence_id=f"spell-p{passage_index if passage_index is not None else 0}-{start}-{end}-{ordinal}",
                phase="spelling",
                passage_index=passage_index,
                ordinal=ordinal,
                base_start=start,
                base_end=end,
                original_text=original,
                proposed_text=suggested,
                mapping_id=None,
                proposal_source=f"model:{provider}",
            )
        )

    candidates.sort(key=lambda candidate: (candidate.passage_index or 0, candidate.base_start))
    for new_ordinal, candidate in enumerate(candidates, start=1):
        expected_id = (
            f"spell-p{candidate.passage_index if candidate.passage_index is not None else 0}-"
            f"{candidate.base_start}-{candidate.base_end}-{new_ordinal}"
        )
        if candidate.ordinal != new_ordinal or candidate.occurrence_id != expected_id:
            candidates[new_ordinal - 1] = Candidate(
                occurrence_id=expected_id,
                phase=candidate.phase,
                passage_index=candidate.passage_index,
                ordinal=new_ordinal,
                base_start=candidate.base_start,
                base_end=candidate.base_end,
                original_text=candidate.original_text,
                proposed_text=candidate.proposed_text,
                mapping_id=candidate.mapping_id,
                proposal_source=candidate.proposal_source,
            )
    return candidates
