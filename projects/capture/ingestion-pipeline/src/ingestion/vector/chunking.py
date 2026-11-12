"""Deterministic sentence-aware vector chunks under a stored highlight."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ingestion.config import EmbeddingChunkConfig

_WORD = re.compile(r"\S+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n{2,}")


@dataclass(frozen=True)
class VectorChunk:
    text: str
    start_char: int
    end_char: int
    sentence_start: int
    sentence_end: int
    hard_split: bool = False


@dataclass(frozen=True)
class _Piece:
    start: int
    end: int
    sentence_index: int
    hard_split: bool = False


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for boundary in _SENTENCE_BOUNDARY.finditer(text):
        trimmed = _trim_span(text, start, boundary.start())
        if trimmed[0] < trimmed[1]:
            spans.append(trimmed)
        start = boundary.end()
    trimmed = _trim_span(text, start, len(text))
    if trimmed[0] < trimmed[1]:
        spans.append(trimmed)
    return spans


def _within_limits(text: str, start: int, end: int, config: EmbeddingChunkConfig) -> bool:
    return bool(
        end - start <= config.max_characters
        and len(_WORD.findall(text[start:end])) <= config.max_words
    )


def _hard_pieces(
    text: str,
    start: int,
    end: int,
    *,
    sentence_index: int,
    config: EmbeddingChunkConfig,
) -> list[_Piece]:
    pieces: list[_Piece] = []
    cursor = start
    while cursor < end:
        character_end = min(end, cursor + config.max_characters)
        words = list(_WORD.finditer(text, cursor, character_end))
        if len(words) > config.max_words:
            split_end = words[config.max_words - 1].end()
        elif character_end < end:
            whitespace = [
                match.start()
                for match in re.finditer(r"\s+", text[cursor:character_end])
            ]
            split_end = cursor + whitespace[-1] if whitespace else character_end
        else:
            split_end = end
        if split_end <= cursor:
            split_end = min(end, cursor + config.max_characters)
        piece_start, piece_end = cursor, split_end
        if piece_start < piece_end:
            pieces.append(
                _Piece(piece_start, piece_end, sentence_index, hard_split=True)
            )
        cursor = split_end
    return pieces


def sentence_chunks(
    text: str, config: EmbeddingChunkConfig
) -> list[VectorChunk]:
    """Create ordered 2–3-sentence chunks with sentence overlap when possible."""
    config.validate()
    sentence_spans = _sentence_spans(text)
    if not sentence_spans:
        return []
    pieces: list[_Piece] = []
    for sentence_index, (start, end) in enumerate(sentence_spans):
        if _within_limits(text, start, end, config):
            pieces.append(_Piece(start, end, sentence_index))
        else:
            pieces.extend(
                _hard_pieces(
                    text,
                    start,
                    end,
                    sentence_index=sentence_index,
                    config=config,
                )
            )

    chunks: list[VectorChunk] = []
    index = 0
    while index < len(pieces):
        first = pieces[index]
        if first.hard_split:
            end_index = index + 1
        else:
            end_index = index
            while end_index < len(pieces):
                candidate = pieces[end_index]
                if candidate.hard_split:
                    break
                if end_index - index >= config.target_sentences:
                    break
                if not _within_limits(
                    text, pieces[index].start, candidate.end, config
                ):
                    break
                end_index += 1
            if end_index == index:
                end_index = index + 1
        selected = pieces[index:end_index]
        start = selected[0].start
        end = selected[-1].end
        chunks.append(
            VectorChunk(
                text=text[start:end],
                start_char=start,
                end_char=end,
                sentence_start=selected[0].sentence_index,
                sentence_end=selected[-1].sentence_index + 1,
                hard_split=any(piece.hard_split for piece in selected),
            )
        )
        if end_index >= len(pieces):
            break
        overlap = (
            min(config.sentence_overlap, len(selected) - 1)
            if not any(piece.hard_split for piece in selected)
            else 0
        )
        index = end_index - overlap

    validate_vector_coverage(text, chunks)
    return chunks


def validate_vector_coverage(text: str, chunks: list[VectorChunk]) -> None:
    """Every non-whitespace character and word must occur in a vector chunk."""
    if not text.strip():
        if chunks:
            raise ValueError("empty vector input produced chunks")
        return
    for index, character in enumerate(text):
        if not character.isspace() and not any(
            chunk.start_char <= index < chunk.end_char for chunk in chunks
        ):
            raise ValueError(f"vector chunk coverage dropped character at {index}")


def _hard_split(text: str, size: int) -> list[str]:
    """Last-resort split at a hard character boundary, without overlap."""
    return [text[index : index + size] for index in range(0, len(text), size)]


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text by paragraph, sentence, then character boundary."""
    sentence_end = re.compile(r"(?<=[.!?])\s+")
    pieces: list[str] = []
    paragraphs = re.split(r"\n\n+", text)
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= chunk_size:
            pieces.append(paragraph)
        else:
            pieces.extend(
                sentence.strip()
                for sentence in sentence_end.split(paragraph)
                if sentence.strip()
            )

    if not pieces:
        return [text]

    final_pieces: list[str] = []
    for piece in pieces:
        if len(piece) <= chunk_size:
            final_pieces.append(piece)
        else:
            final_pieces.extend(_hard_split(piece, chunk_size))
    pieces = final_pieces

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    tail = ""

    for piece in pieces:
        piece_len = len(piece)
        if current and current_len + 1 + piece_len > chunk_size:
            flushed = " ".join(current)
            chunks.append((tail + " " + flushed) if tail else flushed)
            tail = flushed[-overlap:] if overlap else ""
            current = []
            current_len = len(tail)
        current.append(piece)
        current_len += piece_len + (1 if current_len else 0)

    if current:
        flushed = " ".join(current)
        chunks.append((tail + " " + flushed) if tail else flushed)

    return chunks if chunks else [text]


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
    """Structurally chunk text with deterministic overlap."""
    return _chunk_text(text, chunk_size, overlap)
