"""Structural chunking used by the archived vector storage consumer."""

import logging
import re

logger = logging.getLogger(__name__)


def _hard_split(text: str, size: int) -> list[str]:
    """Last-resort split at a hard character boundary, without overlap."""
    logger.debug("hard_split — text_len=%d, size=%d", len(text), size)
    return [text[i : i + size] for i in range(0, len(text), size)]


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text by paragraph, sentence, then character boundary."""
    sentence_end = re.compile(r"(?<=[.!?])\s+")
    pieces: list[str] = []

    for paragraph in re.split(r"\n\n+", text):
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

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    tail = ""

    for piece in final_pieces:
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
    """Structurally chunk text for the archived storage write path."""
    return _chunk_text(text, chunk_size, overlap)
