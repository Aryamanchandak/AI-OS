"""Local RAG chat over saved transcript markdown files."""

from __future__ import annotations

import math
from typing import Optional

from .storage import append_chat_turn, chat_path, read_markdown, require_env, transcript_path

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_CHARS = 1800
CHUNK_OVERLAP = 250
WHOLE_TRANSCRIPT_LIMIT = 32000
HISTORY_LIMIT = 8000


def ask_episode(
    episode_id: str,
    question: str,
    top_k: int = 5,
    chat_model: Optional[str] = None,
    embedding_model: Optional[str] = None,
) -> str:
    """Answer a question against a saved transcript and append the turn to chat history."""
    if not question.strip():
        raise ValueError("question cannot be empty.")

    transcript = read_markdown(transcript_path(episode_id))
    history = _load_chat_history(episode_id)
    context = _select_context(
        transcript=transcript,
        question=question,
        top_k=top_k,
        embedding_model=embedding_model,
    )
    answer = _answer_with_openai(
        question=question,
        context=context,
        history=history,
        model=chat_model,
    )
    append_chat_turn(episode_id, question, answer)
    return answer


def build_retrieval_context(
    episode_id: str,
    question: str,
    top_k: int = 5,
    embedding_model: Optional[str] = None,
) -> str:
    """Return the transcript excerpts that would be sent to the chat model."""
    transcript = read_markdown(transcript_path(episode_id))
    return _select_context(transcript, question, top_k, embedding_model)


def _select_context(
    transcript: str,
    question: str,
    top_k: int,
    embedding_model: Optional[str],
) -> str:
    if len(transcript) <= WHOLE_TRANSCRIPT_LIMIT:
        return transcript

    chunks = _chunk_text(transcript, CHUNK_CHARS, CHUNK_OVERLAP)
    if not chunks:
        raise RuntimeError("Transcript produced no retrievable chunks.")

    client = _openai_client()
    model = embedding_model or DEFAULT_EMBEDDING_MODEL
    inputs = [question] + chunks
    response = client.embeddings.create(model=model, input=inputs)
    vectors = [item.embedding for item in response.data]
    query_vector = vectors[0]
    chunk_vectors = vectors[1:]

    scored = [
        (_cosine_similarity(query_vector, vector), index, chunks[index])
        for index, vector in enumerate(chunk_vectors)
    ]
    scored.sort(reverse=True, key=lambda item: item[0])
    selected = sorted(scored[:top_k], key=lambda item: item[1])

    excerpts = []
    for score, index, chunk in selected:
        excerpts.append(f"## Transcript Excerpt {index + 1} (score {score:.3f})\n\n{chunk}")
    return "\n\n".join(excerpts)


def _answer_with_openai(
    question: str,
    context: str,
    history: str,
    model: Optional[str],
) -> str:
    client = _openai_client()
    messages = [
        {
            "role": "system",
            "content": (
                "Answer questions using only the supplied podcast transcript context and "
                "the prior chat history. If the transcript does not support an answer, say so. "
                "Keep answers direct, scientific, and explicit about uncertainty."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Prior chat history:\n{history or '(none)'}\n\n"
                f"Transcript context:\n{context}\n\n"
                f"Question: {question}"
            ),
        },
    ]
    response = client.chat.completions.create(
        model=model or DEFAULT_CHAT_MODEL,
        messages=messages,
        temperature=0.2,
    )
    answer = response.choices[0].message.content or ""
    if not answer.strip():
        raise RuntimeError("OpenAI returned an empty answer.")
    return answer.strip()


def _openai_client():
    from openai import OpenAI

    require_env("OPENAI_API_KEY")
    return OpenAI()


def _load_chat_history(episode_id: str) -> str:
    path = chat_path(episode_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[-HISTORY_LIMIT:]


def _chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    text = text.strip()
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
