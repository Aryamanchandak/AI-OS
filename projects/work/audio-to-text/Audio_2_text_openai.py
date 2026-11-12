import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# ----------------------------
# API KEY
# ----------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is missing. Add it to the .env file before running "
        "this script."
    )


# ----------------------------
# CONFIG
# ----------------------------
AUDIO_PATH = "Hsbc.m4a"
TRANSCRIPTION_MODEL = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe")
SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-5.6-luna")

# OpenAI's transcription endpoint accepts files up to 25 MB. A lower threshold
# leaves a little room for multipart upload overhead.
MAX_UPLOAD_BYTES = 24 * 1024 * 1024
CHUNK_SECONDS = 20 * 60


# ----------------------------
# CLIENT
# ----------------------------
client = OpenAI(api_key=OPENAI_API_KEY)


TRANSCRIPTION_PROMPT = """
Transcribe the recording exactly as spoken. Preserve wording, punctuation, and
speaker changes where possible. Do not summarize or add commentary.
""".strip()


def split_audio(audio_path: Path, output_dir: Path) -> list[Path]:
    """Convert a large recording into upload-safe MP3 chunks using ffmpeg."""

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "This audio is larger than 24 MB and must be split, but ffmpeg is "
            "not installed. Install ffmpeg and run the script again."
        )

    chunk_pattern = output_dir / "chunk_%03d.mp3"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "48k",
        "-f",
        "segment",
        "-segment_time",
        str(CHUNK_SECONDS),
        "-reset_timestamps",
        "1",
        str(chunk_pattern),
    ]

    print("Audio is larger than 24 MB; creating temporary upload chunks...")
    subprocess.run(command, check=True)

    chunks = sorted(output_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise RuntimeError("ffmpeg did not create any audio chunks.")

    oversized = [chunk for chunk in chunks if chunk.stat().st_size > MAX_UPLOAD_BYTES]
    if oversized:
        raise RuntimeError(
            f"An audio chunk is still too large to upload: {oversized[0].name}"
        )

    return chunks


def transcribe_audio_part(audio_path: Path, context: str = "") -> str:
    """Transcribe one upload-safe audio file with OpenAI."""

    prompt = TRANSCRIPTION_PROMPT
    if context:
        prompt += f"\n\nThe preceding audio ended with:\n{context[-1000:]}"

    with audio_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=TRANSCRIPTION_MODEL,
            file=audio_file,
            prompt=prompt,
        )

    return response.text.strip()


def transcribe_with_openai(audio_path: str) -> str:
    """Transcribe an audio file using OpenAI, splitting large files as needed."""

    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")

    print("Transcribing audio...")

    with tempfile.TemporaryDirectory(prefix="openai_audio_chunks_") as temp_dir:
        if path.stat().st_size <= MAX_UPLOAD_BYTES:
            audio_parts = [path]
        else:
            audio_parts = split_audio(path, Path(temp_dir))

        transcript_parts: list[str] = []
        total_parts = len(audio_parts)

        for index, audio_part in enumerate(audio_parts, start=1):
            print(f"Transcribing part {index} of {total_parts}...")
            previous_context = transcript_parts[-1] if transcript_parts else ""
            transcript_parts.append(
                transcribe_audio_part(audio_part, context=previous_context)
            )

    return "\n\n".join(transcript_parts)


def summarise_with_openai(transcript: str) -> str:
    """Summarise the transcript using OpenAI."""

    response = client.responses.create(
        model=SUMMARY_MODEL,
        input=f"""
Summarise the following transcript.

Return the response in Markdown using exactly these sections.

# Executive Summary

# Key Discussion Points

# Action Items

# Important Decisions

# Open Questions

Transcript:

{transcript}
""",
    )

    return response.output_text


def main() -> None:
    transcript = transcribe_with_openai(AUDIO_PATH)

    Path("transcript.md").write_text(
        transcript,
        encoding="utf-8",
    )

    print("Transcript saved to transcript.md")

    summary = summarise_with_openai(transcript)

    Path("summary.md").write_text(
        summary,
        encoding="utf-8",
    )

    print("Summary saved to summary.md")

    print("\n===== TRANSCRIPT =====\n")
    print(transcript)

    print("\n===== SUMMARY =====\n")
    print(summary)


if __name__ == "__main__":
    main()
