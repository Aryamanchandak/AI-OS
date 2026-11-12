import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


# ----------------------------
# API KEY
# ----------------------------
load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]


# ----------------------------
# CONFIG
# ----------------------------
AUDIO_PATH = "Jefferies.mp3"
MODEL = "gemini-2.5-flash"


# ----------------------------
# CLIENT
# ----------------------------
client = genai.Client(api_key=GEMINI_API_KEY)


def transcribe_with_gemini(audio_path: str) -> str:
    """
    Transcribe an audio file using Gemini.
    """

    print("Uploading audio...")

    audio = client.files.upload(file=audio_path)

    print("Generating transcript...")

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            audio,
            """
You are a professional transcription engine.

Transcribe this audio exactly as spoken.

Instructions:
- Preserve wording.
- Preserve speaker changes where possible.
- Preserve punctuation.
- Do NOT summarise.
- Output ONLY the transcript.
"""
        ],
    )

    return response.text


def summarise_with_gemini(transcript: str) -> str:
    """
    Summarise the transcript using Gemini.
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=f"""
Summarise the following transcript.

Return the response in Markdown using exactly these sections.

# Executive Summary

# Key Discussion Points

# Action Items

# Important Decisions

# Open Questions

Transcript:

{transcript}
"""
    )

    return response.text


def main():

    transcript = transcribe_with_gemini(AUDIO_PATH)

    Path("transcript.md").write_text(
        transcript,
        encoding="utf-8"
    )

    print("Transcript saved to transcript.md")

    summary = summarise_with_gemini(transcript)

    Path("summary.md").write_text(
        summary,
        encoding="utf-8"
    )

    print("Summary saved to summary.md")

    print("\n===== TRANSCRIPT =====\n")
    print(transcript)

    print("\n===== SUMMARY =====\n")
    print(summary)


if __name__ == "__main__":
    main()