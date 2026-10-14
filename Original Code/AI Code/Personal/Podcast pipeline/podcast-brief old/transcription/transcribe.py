"""
transcribe.py — Transcribe audio using Deepgram Nova-3 with speaker diarization.
"""

import json
import re
from pathlib import Path
from typing import Optional

from core.config import TRANSCRIPT_DIR, MODEL_LIGHT, ensure_dirs, require_env
from core.models import Segment, Transcript


# ─── Main entry point ────────────────────────────────────────────────────────

def transcribe(
    audio_path: Path,
    episode_id: str,
    speakers_hint: Optional[str] = None,
    force: bool = False,
) -> Transcript:
    """
    Transcribe audio file with Deepgram. Caches result by episode_id.
    Optionally resolves speaker names from the hint via Claude.
    """
    require_env("DEEPGRAM_API_KEY")
    ensure_dirs()

    cache_path = TRANSCRIPT_DIR / f"{episode_id}.json"
    if cache_path.exists() and not force:
        return Transcript.load(cache_path)

    transcript = _deepgram_transcribe(audio_path, episode_id)

    if speakers_hint and len(transcript.speakers) >= 2:
        transcript = _resolve_speaker_names(transcript, speakers_hint)

    transcript.save(cache_path)
    return transcript


# ─── Deepgram call ───────────────────────────────────────────────────────────

def _deepgram_transcribe(audio_path: Path, episode_id: str) -> Transcript:
    """Send audio to Deepgram Nova-3 and parse the response."""
    import os
    from deepgram import DeepgramClient, PrerecordedOptions, FileSource

    client = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))

    with open(audio_path, "rb") as f:
        audio_buffer = f.read()

    payload: FileSource = {"buffer": audio_buffer}
    options = PrerecordedOptions(
        model="nova-3",
        diarize=True,
        punctuate=True,
        paragraphs=True,
        utterances=True,
        smart_format=True,
        filler_words=False,
    )

    response = client.listen.rest.v("1").transcribe_file(payload, options, timeout=600)
    result = response.to_dict()

    return _parse_deepgram(result, episode_id)


def _parse_deepgram(result: dict, episode_id: str) -> Transcript:
    """Convert Deepgram's response into our Transcript model."""
    utterances = result.get("results", {}).get("utterances", []) or []
    segments = []

    for utt in utterances:
        text = (utt.get("transcript") or "").strip()
        if not text:
            continue
        speaker_num = utt.get("speaker", 0)
        segments.append(Segment(
            speaker=f"Speaker {speaker_num}",
            start=float(utt.get("start", 0.0)),
            end=float(utt.get("end", 0.0)),
            text=text,
        ))

    if not segments:
        channels = result.get("results", {}).get("channels", [])
        if channels and channels[0].get("alternatives"):
            full = channels[0]["alternatives"][0].get("transcript", "")
            if full:
                segments = [Segment(speaker="Speaker 0", start=0.0, end=0.0, text=full)]

    speakers = sorted({s.speaker for s in segments})
    full_text = " ".join(s.text for s in segments)

    return Transcript(
        episode_id=episode_id,
        segments=segments,
        speakers=speakers,
        full_text=full_text,
    )


# ─── Speaker name resolution ─────────────────────────────────────────────────

def _resolve_speaker_names(transcript: Transcript, speakers_hint: str) -> Transcript:
    """
    Use Claude (Haiku) to map "Speaker N" labels to real names based on
    the conversation pattern and the hint.
    """
    from core.llm import call_anthropic
    from core.config import require_env
    require_env("ANTHROPIC_API_KEY")

    sample_lines = []
    for seg in transcript.segments[:30]:
        sample_lines.append(f"[{seg.speaker}] {seg.text[:250]}")
    sample = "\n".join(sample_lines)

    prompt = f"""Here is the start of a podcast transcript with generic speaker labels:

{sample}

Context about this show: {speakers_hint}

Speaker labels found in this transcript: {", ".join(transcript.speakers)}

Based on conversation patterns (who introduces whom, who asks vs. answers, speaking style), map each generic label to the real name.

Return ONLY a JSON object, no preamble. Example:
{{"Speaker 0": "Lex Fridman", "Speaker 1": "Andrej Karpathy"}}

If you cannot confidently identify a speaker, keep their generic label as the value."""

    try:
        text = call_anthropic(
            model=MODEL_LIGHT,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        json_match = re.search(r"\{[^}]+\}", text, re.DOTALL)
        if not json_match:
            return transcript

        mapping = json.loads(json_match.group())

        for seg in transcript.segments:
            if seg.speaker in mapping and mapping[seg.speaker]:
                seg.speaker = mapping[seg.speaker]

        transcript.speakers = sorted({s.speaker for s in transcript.segments})

    except Exception as e:
        print(f"  ⚠ Speaker resolution failed: {e}", flush=True)

    return transcript
