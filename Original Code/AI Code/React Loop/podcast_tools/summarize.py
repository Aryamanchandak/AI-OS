"""OpenAI-powered general scientific summaries for saved transcripts."""

from __future__ import annotations

from typing import Optional

from .storage import (
    make_episode_id,
    read_header_field,
    read_markdown,
    require_env,
    summary_path,
    transcript_path,
    write_summary,
)

# gpt-4o has a 128k-token context window. At ~4 chars/token, 300k chars (~75k
# tokens) leaves ample room for the system prompt and output, so essentially every
# real transcript is summarised in a single detailed pass. The map-reduce path below
# only kicks in for genuinely extreme transcripts and stays purely as a safety net.
DEFAULT_SUMMARY_MODEL = "gpt-4o"
SUMMARY_CHUNK_CHARS = 300000
SUMMARY_MAX_TOKENS = 4000

SUMMARY_SYSTEM_PROMPT = """You write thorough, general-scientific podcast summaries \
that a curious reader could learn from without listening to the episode.
Be substantive and detailed: explain mechanisms, evidence, claims, definitions, \
uncertainty, and implications in full sentences and real paragraphs — not terse \
one-liners. Prefer depth over brevity while staying faithful to the transcript.
Strict rule: do NOT add facts, numbers, or quotes that are not supported by the \
transcript. If something is unclear or unstated, say so rather than inventing it.

Structure every summary in markdown with these sections:
- **Overview** — a full paragraph framing what the episode is about and why it matters.
- **Key Concepts / Themes** — each major theme as a bolded point followed by 2-4 \
sub-bullets that actually explain it.
- **Evidence & Uncertainties** — the concrete claims, data, or examples given, and \
where the speakers hedge or disagree.
- **Notable Quotes** — a few verbatim lines that appear in the transcript (quote them \
exactly; omit this section if the transcript has no quotable lines).
- **Implications / Takeaways** — what follows from the discussion in practice."""


def summarize_episode(episode_id: str, title: str = "", model: Optional[str] = None) -> str:
    """Read ``data/transcripts/<episode_id>.md``, summarize it, save markdown, return path."""
    transcript = read_markdown(transcript_path(episode_id))
    # Fall back to the title captured in the transcript header (e.g. the real YouTube
    # video title) so the summary isn't labelled with the bare episode_id.
    resolved_title = title or read_header_field(transcript, "title") or episode_id
    summary = summarize_transcript_text(transcript, model=model)
    return write_summary(
        episode_id=episode_id,
        summary=summary,
        title=resolved_title,
        transcript_id=episode_id,
    )


def summarize_transcript_text(transcript: str, model: Optional[str] = None) -> str:
    """Summarize transcript text with a map-reduce path for long episodes."""
    if not transcript.strip():
        raise ValueError("transcript cannot be empty.")

    chunks = _chunk_text(transcript, SUMMARY_CHUNK_CHARS)
    if len(chunks) == 1:
        return _openai_chat(
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": _summary_prompt(chunks[0])},
            ],
            model=model,
        )

    partials = []
    for index, chunk in enumerate(chunks, start=1):
        partials.append(
            _openai_chat(
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Summarize transcript chunk {index} of {len(chunks)}. "
                            "Preserve important claims, evidence, caveats, and terminology.\n\n"
                            f"{chunk}"
                        ),
                    },
                ],
                model=model,
            )
        )

    combined = "\n\n".join(f"## Chunk {i}\n\n{text}" for i, text in enumerate(partials, 1))
    return _openai_chat(
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Synthesize these chunk summaries into ONE coherent, detailed "
                    "general-scientific podcast summary using the full section "
                    "structure from your instructions (Overview, Key Concepts / "
                    "Themes, Evidence & Uncertainties, Notable Quotes, Implications / "
                    "Takeaways). Merge overlapping points, keep the depth, and do not "
                    "introduce anything absent from the chunk summaries.\n\n"
                    f"{combined}"
                ),
            },
        ],
        model=model,
    )


def summarize_youtube_video(
    video_url: str,
    title: str = "",
    prefer_captions: bool = True,
    model: Optional[str] = None,
) -> dict:
    """Summarise any YouTube video end to end: transcribe then summarise.

    Uses YouTube captions when available (free, no Deepgram) and falls back to audio
    transcription only when captions are missing. Returns the ``episode_id`` and the
    saved transcript/summary paths plus the summary text.
    """
    # Imported here (not at module top) to avoid an import cycle: transcription
    # imports ingestion/storage, never summarize.
    from .transcription import transcribe_source

    episode_id = make_episode_id(video_url)
    transcript_file = transcribe_source(
        video_url,
        title=title,
        episode_id=episode_id,
        platform="youtube",
        prefer_captions=prefer_captions,
    )
    summary_file = summarize_episode(episode_id, title=title, model=model)
    return {
        "episode_id": episode_id,
        "transcript_path": transcript_file,
        "summary_path": summary_file,
        "summary": read_markdown(summary_path(episode_id)),
    }


def summary_exists(episode_id: str) -> bool:
    return summary_path(episode_id).exists()


def _summary_prompt(transcript: str) -> str:
    return (
        "Write a detailed general-scientific markdown summary of this podcast "
        "transcript, following the full section structure from your instructions "
        "(Overview, Key Concepts / Themes, Evidence & Uncertainties, Notable Quotes, "
        "Implications / Takeaways). Be thorough and explanatory; a reader should come "
        "away understanding the substance of the episode. Only use what the transcript "
        "supports.\n\n"
        f"{transcript}"
    )


def _openai_chat(messages: list[dict], model: Optional[str] = None) -> str:
    from openai import OpenAI

    require_env("OPENAI_API_KEY")
    client = OpenAI()
    response = client.chat.completions.create(
        model=model or DEFAULT_SUMMARY_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=SUMMARY_MAX_TOKENS,
    )
    content = response.choices[0].message.content or ""
    if not content.strip():
        raise RuntimeError("OpenAI returned an empty summary.")
    return content.strip()


def _chunk_text(text: str, max_chars: int) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph.strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= max_chars:
            current = paragraph.strip()
        else:
            chunks.extend(paragraph[i:i + max_chars] for i in range(0, len(paragraph), max_chars))
            current = ""
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]
