import os
import uuid
import wave

from google import genai
from google.genai import types
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("podcast")

PODCAST_STYLES = {
    "financial": (
        "You are creating a professional financial podcast.\n\n"
        "Requirements:\n"
        "- Natural conversational style\n"
        "- Not robotic\n"
        "- Focus on investment insights\n"
        "- Discuss: Business Overview, Industry Overview, Financial Performance\n"
        "- Explain numbers in simple language\n"
        "- Make it sound like a real investing podcast\n"
        "- Keep it concise — approximately 1-2 minutes\n"
    ),
    "general": (
        "You are creating an engaging general-audience podcast.\n\n"
        "Requirements:\n"
        "- Warm, conversational tone\n"
        "- Accessible to a broad audience\n"
        "- Highlight key ideas and interesting facts\n"
        "- Keep it engaging and concise — approximately 1-2 minutes\n"
    ),
}


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set.")
    return genai.Client(api_key=api_key)


@mcp.tool()
def generate_podcast_transcript(content: str, style: str = "financial") -> str:
    """
    Generate a podcast-style spoken transcript from any input text using Gemini.

    content: the source material to convert — annual report analysis, news brief,
             research note, article, or any other text.
    style:   controls the tone and focus. Valid values:
             'financial' (investment-focused, 1-2 min),
             'general'   (broad audience, warm tone, 1-2 min).

    Returns the transcript as a plain string ready for TTS.
    Use synthesize_podcast_audio or run_podcast_pipeline to convert it to audio.
    """
    if not content or not content.strip():
        raise ValueError("content cannot be empty.")
    if style not in PODCAST_STYLES:
        raise ValueError(
            f"Unknown style '{style}'. "
            f"Valid styles: {', '.join(PODCAST_STYLES.keys())}"
        )

    client = _get_client()
    prompt = f"{PODCAST_STYLES[style]}\nCONTENT TO COVER:\n\n{content}"

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
    except Exception as e:
        raise RuntimeError(f"generate_podcast_transcript: Gemini call failed. {e}") from e

    return response.text


@mcp.tool()
def synthesize_podcast_audio(
    transcript: str,
    voice_name: str = "Kore",
    output_path: str | None = None,
) -> str:
    """
    Convert a podcast transcript to a WAV audio file using Gemini TTS.

    transcript:  plain text transcript, e.g. from generate_podcast_transcript.
    voice_name:  Gemini prebuilt voice. Default: 'Kore'.
    output_path: where to save the WAV file. If None, saves to /tmp/podcast_<uuid>.wav.

    Returns the absolute path to the saved WAV file.
    """
    if not transcript or not transcript.strip():
        raise ValueError("transcript cannot be empty.")

    if output_path is None:
        output_path = f"/tmp/podcast_{uuid.uuid4().hex}.wav"
    output_path = os.path.abspath(output_path)

    client = _get_client()

    try:
        tts_response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=transcript,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
            ),
        )
    except Exception as e:
        raise RuntimeError(f"synthesize_podcast_audio: Gemini TTS call failed. {e}") from e

    audio_data = None
    try:
        audio_data = tts_response.candidates[0].content.parts[0].inline_data.data
    except (IndexError, AttributeError):
        pass

    if not audio_data:
        raise RuntimeError(
            "synthesize_podcast_audio: Gemini TTS returned no audio. "
            "Check that the transcript is non-empty and the model is available."
        )

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(audio_data)

    return output_path


@mcp.tool()
def run_podcast_pipeline(
    content: str,
    style: str = "financial",
    voice_name: str = "Kore",
    output_path: str | None = None,
) -> str:
    """
    Convert any text into a podcast audio file in one step.

    Steps: generate transcript from content → synthesize WAV audio.

    content:     source material — any text (ARA output, news brief, article, etc.).
    style:       'financial' (investment-focused) or 'general' (broad audience).
    voice_name:  Gemini prebuilt voice. Default: 'Kore'.
    output_path: path to save the WAV file. If None, saves to /tmp/podcast_<uuid>.wav.

    Returns the absolute path to the saved WAV audio file.
    Call generate_podcast_transcript separately if you also need the transcript text.
    """
    transcript = generate_podcast_transcript(content, style)
    return synthesize_podcast_audio(transcript, voice_name, output_path)
