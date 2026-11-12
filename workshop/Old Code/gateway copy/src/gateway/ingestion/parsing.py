"""Lossless semantic segmentation for normalized ingestion documents.

Inspection windows, stored highlights, extraction context, and vector chunks
are intentionally separate concepts. The model sees bounded windows and emits
only a small boundary decision; accepted highlights are always exact slices of
the normalized source, and a coverage check runs before persistence.
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from gateway.ingestion.config import SegmentationConfig

CONTEXT_ELISION = "[…]"

_WORD = re.compile(r"\S+")
_HEADING = re.compile(r"(?m)^#{1,6}\s+.+$")
_HEADING_TEXT = re.compile(r"(?m)^#{1,6}\s+(.+)$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

SEGMENTATION_PROMPT_TEMPLATE = """\
You are a markdown document segmenter.

Inspect this bounded window from a larger document:

---
{block}
---

The parser found these valid source boundaries. Each ID points to the exact
start of the quoted source excerpt:

{candidates}

Decide whether a clearly distinct broad topic or section begins inside this
window. Do not split examples, evidence, results, conclusions, or supporting
details that still discuss the same main subject.

Return a JSON object with:
- "has_second_topic": true only when a distinct topic begins in this window.
- "boundary_id": when true, the integer ID of exactly one listed boundary;
  otherwise null.

Never create an ID or return document text. If none of the listed boundaries
starts a clearly distinct topic, return false and null.\
"""


class SegmentationFailure(RuntimeError):
    """A typed, document-scoped failure that must leave parsing pending."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        attempts: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.attempts = attempts or []


@dataclass(frozen=True)
class BoundaryDecision:
    has_second_topic: bool
    boundary_id: int | None = None
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    stop_reason: str | None = None


@dataclass(frozen=True)
class BoundaryCandidate:
    """A parser-derived source boundary the model is allowed to select."""

    id: int
    offset: int
    excerpt: str


@dataclass(frozen=True)
class Highlight:
    """One atomic unit of the pipeline, with exact document provenance."""

    index: int
    text: str
    context_text: str | None
    heading: str | None
    start_char: int
    end_char: int
    start_word: int
    end_word: int
    segmentation: dict[str, Any] = field(default_factory=dict)


class TopicSegmenter(Protocol):
    def boundary_decision(
        self, block: str, candidates: list[BoundaryCandidate]
    ) -> BoundaryDecision: ...


class ChatClient(Protocol):
    def chat(
        self,
        prompt: str | None = None,
        *,
        system: Any = None,
        profile: str | None = None,
        provider: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        response_format: Any = None,
    ) -> dict[str, Any]: ...

    def resolve_chat_profile(self, profile: str) -> dict[str, Any]: ...


class HeadingTopicSegmenter:
    """Explicit deterministic/offline segmenter used by tests."""

    def second_topic(self, block: str) -> str:
        headings = list(_HEADING.finditer(block))
        return block[headings[1].start() :].strip() if len(headings) > 1 else ""

    def boundary_decision(
        self,
        block: str,
        candidates: list[BoundaryCandidate] | None = None,
    ) -> BoundaryDecision:
        allowed = (
            candidates
            if candidates is not None
            else _candidate_boundaries(block, block_start=0, open_start=0)
        )
        second = self.second_topic(block)
        if not second:
            return BoundaryDecision(False)
        offset = block.find(second)
        matching = [candidate for candidate in allowed if candidate.offset == offset]
        if matching:
            return BoundaryDecision(True, boundary_id=matching[0].id)
        raise SegmentationFailure(
            "invalid_boundary_id",
            "Deterministic heading did not match a parser-offered boundary",
        )


class GatewayTopicSegmenter:
    """Pinned Phi-4 boundary selector routed through the shared gateway."""

    def __init__(
        self,
        *,
        chat_client: ChatClient,
        config: SegmentationConfig,
    ) -> None:
        self._client = chat_client
        self.config = config
        self.profile = config.chat_profile
        self._resolved: dict[str, str] | None = None

    def _resolve(self) -> dict[str, str]:
        if self._resolved is not None:
            return self._resolved
        try:
            resolved = self._client.resolve_chat_profile(self.profile)
        except Exception as exc:
            raise SegmentationFailure(
                "profile_unavailable",
                f"Cannot resolve segmentation profile {self.profile!r}: {exc}",
            ) from exc
        provider = str(resolved.get("provider", ""))
        model = str(resolved.get("model", ""))
        if (
            provider != self.config.required_provider
            or model != self.config.required_model
        ):
            raise SegmentationFailure(
                "profile_route_mismatch",
                (
                    f"{self.profile!r} resolved to {provider}/{model}; expected "
                    f"{self.config.required_provider}/{self.config.required_model}"
                ),
                attempts=[{"resolved_provider": provider, "resolved_model": model}],
            )
        self._resolved = {"provider": provider, "model": model}
        return self._resolved

    def effective_configuration(self) -> dict[str, Any]:
        return {
            **self.config.report(),
            "resolved_provider": (
                self._resolved["provider"] if self._resolved is not None else None
            ),
            "resolved_model": (
                self._resolved["model"] if self._resolved is not None else None
            ),
        }

    def boundary_decision(
        self,
        block: str,
        candidates: list[BoundaryCandidate] | None = None,
    ) -> BoundaryDecision:
        resolved = self._resolve()
        allowed = candidates or []
        candidate_ids = [candidate.id for candidate in allowed]
        schema = _boundary_response_schema(candidate_ids)
        candidate_text = "\n".join(
            f'{candidate.id}: {json.dumps(candidate.excerpt, ensure_ascii=False)}'
            for candidate in allowed
        ) or "(none)"
        try:
            response = self._client.chat(
                SEGMENTATION_PROMPT_TEMPLATE.format(
                    block=block, candidates=candidate_text
                ),
                profile=self.profile,
                max_tokens=self.config.max_output_tokens,
                temperature=0.0,
                response_format={
                    "type": "json_schema",
                    "schema": schema,
                    "name": "document_segmentation_boundary",
                },
            )
        except SegmentationFailure:
            raise
        except Exception as exc:
            raise SegmentationFailure(
                "model_unavailable",
                f"Segmentation model call failed: {type(exc).__name__}: {exc}",
            ) from exc
        if not isinstance(response, dict):
            raise SegmentationFailure(
                "invalid_response", "Gateway returned a non-object response"
            )
        if response.get("stop_reason") == "max_tokens":
            raise SegmentationFailure(
                "truncated_response",
                (
                    "Segmentation response reached max_tokens "
                    f"({self.config.max_output_tokens})"
                ),
                attempts=[{"response": response}],
            )
        provider = str(response.get("provider", ""))
        model = str(response.get("model", ""))
        if provider != resolved["provider"] or model != resolved["model"]:
            raise SegmentationFailure(
                "response_route_mismatch",
                (
                    f"Gateway response came from {provider}/{model}; resolved route is "
                    f"{resolved['provider']}/{resolved['model']}"
                ),
                attempts=[{"response": response}],
            )
        parsed = response.get("parsed")
        if parsed is None and isinstance(response.get("text"), str):
            try:
                parsed = json.loads(str(response["text"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
        if not isinstance(parsed, dict) or set(parsed) != {
            "has_second_topic",
            "boundary_id",
        }:
            raise SegmentationFailure(
                "invalid_structure",
                "Segmentation response did not match the boundary schema",
                attempts=[{"response": response}],
            )
        has_second_topic = parsed.get("has_second_topic")
        boundary_id = parsed.get("boundary_id")
        if not isinstance(has_second_topic, bool):
            raise SegmentationFailure(
                "invalid_structure", "has_second_topic must be a boolean"
            )
        if has_second_topic:
            if (
                not isinstance(boundary_id, int)
                or isinstance(boundary_id, bool)
                or boundary_id not in candidate_ids
            ):
                raise SegmentationFailure(
                    "invalid_boundary_id",
                    "A second topic requires one of the offered boundary IDs",
                )
        elif boundary_id is not None:
            raise SegmentationFailure(
                "invalid_structure",
                "A one-topic response must use a null boundary_id",
            )
        return BoundaryDecision(
            has_second_topic=has_second_topic,
            boundary_id=boundary_id,
            provider=provider,
            model=model,
            input_tokens=_optional_int(response.get("input_tokens")),
            output_tokens=_optional_int(response.get("output_tokens")),
            stop_reason=str(response.get("stop_reason", "")) or None,
        )

    def second_topic(self, block: str) -> str:
        """Compatibility view for callers that only need the selected source text."""
        candidates = _candidate_boundaries(block, block_start=0, open_start=0)
        decision = self.boundary_decision(block, candidates)
        if decision.boundary_id is None:
            return ""
        candidate = _candidate_by_id(candidates, decision.boundary_id)
        return block[candidate.offset :] if candidate is not None else ""


def _boundary_response_schema(candidate_ids: list[int]) -> dict[str, Any]:
    boundary_id_schema: dict[str, Any] = {"type": ["integer", "null"]}
    if candidate_ids:
        boundary_id_schema["enum"] = [*candidate_ids, None]
    else:
        boundary_id_schema["enum"] = [None]
    return {
        "type": "object",
        "properties": {
            "has_second_topic": {"type": "boolean"},
            "boundary_id": boundary_id_schema,
        },
        "required": ["has_second_topic", "boundary_id"],
        "additionalProperties": False,
    }


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None


def _heading_of(text: str) -> str | None:
    match = _HEADING_TEXT.search(text)
    return match.group(1).strip() if match else None


def _word_number(source: str, char_offset: int) -> int:
    return len(_WORD.findall(source[:char_offset]))


def _sentences(text: str) -> list[str]:
    return [piece.strip() for piece in _SENTENCE_END.split(text) if piece.strip()]


def context_window(
    document: str,
    start_char: int,
    end_char: int,
    *,
    sentences: int | None = None,
    sentences_before: int | None = None,
    sentences_after: int | None = None,
) -> str | None:
    """Return bounded surrounding sentences without merging them into evidence."""
    if sentences is not None:
        if sentences_before is not None or sentences_after is not None:
            raise ValueError("sentences cannot be combined with side-specific sizes")
        sentences_before = sentences
        sentences_after = sentences
    before_count = 3 if sentences_before is None else sentences_before
    after_count = 3 if sentences_after is None else sentences_after
    if before_count < 0 or after_count < 0:
        raise ValueError("context sentence counts cannot be negative")
    before = (
        " ".join(_sentences(document[:start_char])[-before_count:])
        if before_count
        else ""
    )
    after = (
        " ".join(_sentences(document[end_char:])[:after_count])
        if after_count
        else ""
    )
    if before and after:
        return f"{before} {CONTEXT_ELISION} {after}"
    if before:
        return f"{before} {CONTEXT_ELISION}"
    if after:
        return f"{CONTEXT_ELISION} {after}"
    return None


def _content_bounds(document: str) -> tuple[int, int] | None:
    first = _WORD.search(document)
    if first is None:
        return None
    matches = list(_WORD.finditer(document))
    return first.start(), matches[-1].end()


def _estimated_tokens(text: str) -> int:
    # Conservative and deterministic without importing a model-specific
    # tokenizer. The hard gateway/model context check remains authoritative.
    return max(1, (len(text) + 3) // 4)


def _window_end(
    document: str,
    start: int,
    document_end: int,
    config: SegmentationConfig,
) -> int:
    words = list(_WORD.finditer(document, start, document_end))
    if not words:
        return document_end
    count = min(len(words), config.inspection_target_words)
    while count:
        end = document_end if count == len(words) else words[count - 1].end()
        if _estimated_tokens(document[start:end]) <= config.max_input_tokens:
            return end
        count -= 1
    raise SegmentationFailure(
        "input_budget_exceeded",
        f"No complete word fits the {config.max_input_tokens}-token input budget",
    )


def _candidate_boundaries(
    document: str,
    *,
    block_start: int,
    open_start: int,
    block_end: int | None = None,
) -> list[BoundaryCandidate]:
    """Enumerate source-derived choices; model output can never create an offset."""
    end = len(document) if block_end is None else block_end
    offsets: set[int] = set()
    for match in re.finditer(r"(?m)^[ \t]*(?=\S)", document):
        offsets.add(match.end())
    for match in _SENTENCE_END.finditer(document):
        offsets.add(match.end())

    usable = sorted(
        offset
        for offset in offsets
        if block_start <= offset < end and offset > open_start
    )
    candidates: list[BoundaryCandidate] = []
    for candidate_id, absolute in enumerate(usable, start=1):
        excerpt_end = min(end, absolute + 160)
        excerpt = " ".join(document[absolute:excerpt_end].split())
        if excerpt_end < end:
            excerpt = f"{excerpt}…"
        candidates.append(
            BoundaryCandidate(
                id=candidate_id,
                offset=absolute - block_start,
                excerpt=excerpt,
            )
        )
    return candidates


def _candidate_by_id(
    candidates: list[BoundaryCandidate], boundary_id: int
) -> BoundaryCandidate | None:
    return next(
        (candidate for candidate in candidates if candidate.id == boundary_id), None
    )


def _legacy_boundary_decision(
    segmenter: Any,
    block: str,
    candidates: list[BoundaryCandidate],
) -> BoundaryDecision:
    """Adapt the old deterministic test seam without weakening live routing."""
    method = getattr(segmenter, "boundary_decision", None)
    if callable(method):
        parameters = inspect.signature(method).parameters
        decision = method(block, candidates) if len(parameters) >= 2 else method(block)
        if not isinstance(decision, BoundaryDecision):
            raise SegmentationFailure(
                "invalid_segmenter_result",
                "boundary_decision must return BoundaryDecision",
            )
        return decision
    legacy = getattr(segmenter, "second_topic", None)
    if not callable(legacy):
        raise SegmentationFailure(
            "invalid_segmenter", "Segmenter has no boundary_decision method"
        )
    second = legacy(block)
    if not isinstance(second, str):
        raise SegmentationFailure(
            "invalid_segmenter_result", "second_topic must return a string"
        )
    anchor = second.strip()
    matching = [
        candidate
        for candidate in candidates
        if anchor and block.startswith(anchor, candidate.offset)
    ]
    if len(matching) == 1:
        return BoundaryDecision(True, boundary_id=matching[0].id)
    if not anchor:
        return BoundaryDecision(False)
    occurrences = [match.start() for match in re.finditer(re.escape(anchor), block)]
    if not occurrences:
        raise SegmentationFailure(
            "non_verbatim_anchor", "legacy boundary text is not verbatim in the window"
        )
    if len(matching) > 1:
        raise SegmentationFailure(
            "ambiguous_anchor",
            "legacy boundary text does not identify one offered boundary",
        )
    raise SegmentationFailure(
        "invalid_boundary_id", "legacy boundary text is not at an offered boundary"
    )


def validate_highlight_coverage(
    normalized_content: str, highlights: list[Highlight]
) -> dict[str, int]:
    """Fail unless ordered exact spans cover every normalized word/character."""
    bounds = _content_bounds(normalized_content)
    if bounds is None:
        if highlights:
            raise SegmentationFailure(
                "coverage_failure", "Whitespace-only input produced highlights"
            )
        return {"document_words": 0, "covered_words": 0}
    if not highlights:
        raise SegmentationFailure(
            "coverage_failure", "Non-empty input produced no highlights"
        )
    first_char, final_char = bounds
    cursor = first_char
    for expected_index, highlight in enumerate(highlights):
        if highlight.index != expected_index:
            raise SegmentationFailure(
                "coverage_failure", "Highlight indices are not contiguous"
            )
        if highlight.start_char < cursor:
            raise SegmentationFailure(
                "coverage_failure", "Highlight spans overlap or are out of order"
            )
        if normalized_content[cursor : highlight.start_char].strip():
            raise SegmentationFailure(
                "coverage_failure", "Non-whitespace text is missing between highlights"
            )
        if (
            normalized_content[highlight.start_char : highlight.end_char]
            != highlight.text
        ):
            raise SegmentationFailure(
                "coverage_failure", "Highlight text is not its exact source span"
            )
        cursor = highlight.end_char
    if normalized_content[cursor:final_char].strip():
        raise SegmentationFailure(
            "coverage_failure", "Non-whitespace text is missing after the last highlight"
        )
    word_spans = list(_WORD.finditer(normalized_content[first_char:final_char]))
    covered_words = 0
    for word in word_spans:
        start = first_char + word.start()
        end = first_char + word.end()
        owners = [
            highlight
            for highlight in highlights
            if highlight.start_char <= start and end <= highlight.end_char
        ]
        if len(owners) != 1:
            raise SegmentationFailure(
                "coverage_failure",
                f"Word at [{start}, {end}) belongs to {len(owners)} highlights",
            )
        covered_words += 1
    return {"document_words": len(word_spans), "covered_words": covered_words}


def _highlight(
    document: str,
    *,
    index: int,
    start: int,
    end: int,
    segmentation: dict[str, Any],
    config: SegmentationConfig,
    context_text: str | None = None,
) -> Highlight:
    while start < end and document[start].isspace():
        start += 1
    while end > start and document[end - 1].isspace():
        end -= 1
    text = document[start:end]
    return Highlight(
        index=index,
        text=text,
        context_text=(
            context_text
            if context_text is not None
            else context_window(
                document,
                start,
                end,
                sentences_before=config.context_sentences_before,
                sentences_after=config.context_sentences_after,
            )
        ),
        heading=_heading_of(text),
        start_char=start,
        end_char=end,
        start_word=_word_number(document, start),
        end_word=_word_number(document, end),
        segmentation=segmentation,
    )


def split_into_highlights(
    normalized_content: str,
    *,
    segmenter: TopicSegmenter | Any | None = None,
    config: SegmentationConfig | None = None,
    boundary_origin: Literal["document_segment", "user_selection"] = "document_segment",
    supplied_context_text: str | None = None,
    parent_start_char: int | None = None,
    parent_end_char: int | None = None,
    containing_sentence: str | None = None,
    supplied_selections: list[dict[str, Any]] | None = None,
) -> list[Highlight]:
    """Return exact, losslessly covering highlights or raise a typed failure."""
    policy = config or SegmentationConfig()
    policy.validate()
    bounds = _content_bounds(normalized_content)
    if bounds is None:
        return []
    content_start, content_end = bounds
    document_words = len(_WORD.findall(normalized_content))

    if boundary_origin == "user_selection":
        if supplied_selections is not None:
            highlights: list[Highlight] = []
            previous_end = -1
            for index, selection in enumerate(supplied_selections):
                start = selection.get("source_start_char")
                end = selection.get("source_end_char")
                if not isinstance(start, int) or not isinstance(end, int):
                    raise SegmentationFailure(
                        "invalid_producer_selection",
                        "Producer selections require integer source offsets",
                    )
                if start < 0 or end <= start or end > len(normalized_content):
                    raise SegmentationFailure(
                        "invalid_producer_selection",
                        f"Producer selection [{start}, {end}) is outside its source",
                    )
                if start < previous_end:
                    raise SegmentationFailure(
                        "invalid_producer_selection",
                        "Producer selections must be ordered and non-overlapping",
                    )
                if not normalized_content[start:end].strip():
                    raise SegmentationFailure(
                        "invalid_producer_selection",
                        "Producer selection contains no non-whitespace text",
                    )
                selection_provenance = {
                    "boundary_origin": "user_selection",
                    "outcome": "producer_supplied_boundary",
                    "document_words": document_words,
                    "config": policy.report(),
                    "parent_source_ref": selection.get("parent_source_ref"),
                    "parent_start_char": selection.get("parent_start_char"),
                    "parent_end_char": selection.get("parent_end_char"),
                    "containing_sentence": selection.get("containing_sentence"),
                    "coverage": {
                        "mode": "selected_spans",
                        "selection_count": len(supplied_selections),
                    },
                }
                highlights.append(
                    _highlight(
                        normalized_content,
                        index=index,
                        start=start,
                        end=end,
                        segmentation=selection_provenance,
                        config=policy,
                        context_text=selection.get("context_text"),
                    )
                )
                previous_end = end
            return highlights
        provenance: dict[str, Any] = {
            "boundary_origin": "user_selection",
            "outcome": "producer_supplied_boundary",
            "document_words": document_words,
            "config": policy.report(),
            "parent_start_char": parent_start_char,
            "parent_end_char": parent_end_char,
            "containing_sentence": containing_sentence,
        }
        highlights = [
            _highlight(
                normalized_content,
                index=0,
                start=content_start,
                end=content_end,
                segmentation=provenance,
                config=policy,
                context_text=supplied_context_text,
            )
        ]
        coverage = validate_highlight_coverage(normalized_content, highlights)
        provenance["coverage"] = coverage
        return highlights

    if document_words <= policy.passthrough_max_words:
        provenance = {
            "boundary_origin": "document_segment",
            "outcome": "short_document_passthrough",
            "document_words": document_words,
            "config": policy.report(),
        }
        highlights = [
            _highlight(
                normalized_content,
                index=0,
                start=content_start,
                end=content_end,
                segmentation=provenance,
                config=policy,
            )
        ]
        coverage = validate_highlight_coverage(normalized_content, highlights)
        provenance["coverage"] = coverage
        return highlights

    if segmenter is None:
        raise SegmentationFailure(
            "segmenter_not_configured",
            "Documents over the pass-through limit require an explicit segmenter",
        )

    spans: list[tuple[int, int, dict[str, Any]]] = []
    open_start = content_start
    scan_start = content_start
    windows: list[dict[str, Any]] = []
    started_by: dict[str, Any] | None = None

    while scan_start < content_end:
        raw_end = _window_end(normalized_content, scan_start, content_end, policy)
        raw_window = normalized_content[scan_start:raw_end]
        block = raw_window.strip()
        block_start = scan_start + raw_window.find(block)
        if not block:
            break
        candidates = _candidate_boundaries(
            normalized_content,
            block_start=block_start,
            open_start=open_start,
            block_end=block_start + len(block),
        )
        attempt: dict[str, Any] = {
            "attempt": 1,
            "window_start_char": block_start,
            "window_end_char": block_start + len(block),
            "window_start_word": _word_number(normalized_content, block_start),
            "window_end_word": _word_number(
                normalized_content, block_start + len(block)
            ),
            "window_words": len(_WORD.findall(block)),
            "estimated_input_tokens": _estimated_tokens(block),
            "inspection_target_words": policy.inspection_target_words,
            "max_input_tokens": policy.max_input_tokens,
            "max_output_tokens": policy.max_output_tokens,
            "boundary_candidate_count": len(candidates),
        }
        try:
            decision = _legacy_boundary_decision(segmenter, block, candidates)
        except SegmentationFailure as exc:
            attempt["failure_type"] = exc.code
            attempt["error"] = str(exc)
            attempt["details"] = exc.attempts
            raise SegmentationFailure(
                exc.code, str(exc), attempts=[*windows, attempt]
            ) from exc
        except Exception as exc:
            attempt["failure_type"] = "segmenter_exception"
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            raise SegmentationFailure(
                "segmenter_exception",
                attempt["error"],
                attempts=[*windows, attempt],
            ) from exc

        attempt.update(
            {
                "has_second_topic": decision.has_second_topic,
                "boundary_id": decision.boundary_id,
                "provider": decision.provider,
                "model": decision.model,
                "input_tokens": decision.input_tokens,
                "output_tokens": decision.output_tokens,
                "stop_reason": decision.stop_reason,
            }
        )
        windows.append(attempt)

        if decision.has_second_topic:
            selected = (
                _candidate_by_id(candidates, decision.boundary_id)
                if decision.boundary_id is not None
                else None
            )
            if selected is not None:
                boundary = block_start + selected.offset
            else:
                raise SegmentationFailure(
                    "invalid_boundary_id",
                    "A second-topic decision omitted a valid boundary ID",
                    attempts=windows,
                )
            spans.append(
                (
                    open_start,
                    boundary,
                    {
                        "boundary_origin": "document_segment",
                        "outcome": "semantic_boundary",
                        "document_words": document_words,
                        "config": policy.report(),
                        "started_by": started_by,
                        "windows": windows,
                    },
                )
            )
            started_by = {
                "boundary_id": decision.boundary_id,
                "candidate_excerpt": selected.excerpt,
                "start_char": boundary,
                "provider": decision.provider,
                "model": decision.model,
            }
            open_start = boundary
            scan_start = boundary
            windows = []
            continue

        scan_start = raw_end

    spans.append(
        (
            open_start,
            content_end,
            {
                "boundary_origin": "document_segment",
                "outcome": "document_end",
                "document_words": document_words,
                "config": policy.report(),
                "started_by": started_by,
                "windows": windows,
            },
        )
    )
    highlights = [
        _highlight(
            normalized_content,
            index=index,
            start=start,
            end=end,
            segmentation=provenance,
            config=policy,
        )
        for index, (start, end, provenance) in enumerate(spans)
    ]
    coverage = validate_highlight_coverage(normalized_content, highlights)
    for highlight in highlights:
        highlight.segmentation["coverage"] = coverage
    return highlights
