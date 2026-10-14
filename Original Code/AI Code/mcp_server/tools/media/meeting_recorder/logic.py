import os

from google import genai
from google.genai import types
from mcp.server.fastmcp import FastMCP

from shared.backend_utils import get_gemini_file

mcp = FastMCP("meeting")

MODEL = "gemini-3-flash-preview"

SUMMARY_PROMPT = """
You are a senior research analyst responsible for preparing an institutional-grade discussion summary based ONLY on the contents of a meeting transcript or recording.

Your task is to faithfully extract and organize information that was EXPLICITLY stated during the discussion.

CRITICAL INSTRUCTIONS:

- Do NOT infer.
- Do NOT extrapolate.
- Do NOT speculate.
- Do NOT complete missing context.
- Do NOT assume typical industry dynamics.
- Do NOT generate strategic implications unless they were explicitly stated by the speaker.
- Do NOT create conclusions, risks, opportunities, priorities, or outlooks unless they were directly discussed.
- If the source discussion is short, incomplete, vague, fragmented, or lacking detail, the output MUST remain short, fragmented, and limited accordingly.
- Never add "standard" investment commentary to make the report appear more complete.
- Absence of information is preferable to fabricated completeness.

STRICT GROUNDING REQUIREMENT:

Every statement in the report must be traceable to something explicitly mentioned in the discussion.

If a point was ambiguous or uncertain in the discussion:
- clearly label it as unclear or tentative
- do not resolve ambiguity yourself

If numerical data was mentioned:
- reproduce it exactly as stated
- do not estimate or normalize figures

STYLE REQUIREMENTS:

- Use concise institutional language.
- Prefer factual bullet points over narrative expansion.
- Avoid decorative or analytical writing.
- Avoid adding transitions that imply causality unless explicitly stated.
- Do not use tables.
- Do not include introductions or conclusions unless explicitly supported by the discussion.

OUTPUT PHILOSOPHY:

The objective is accuracy and fidelity to the discussion — NOT completeness.

A very short discussion should produce a very short report.

If only three substantive points were discussed, output only those three points.
"""


def _make_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set.")
    return genai.Client(api_key=api_key)


@mcp.tool()
def transcribe_audio(file_uri: str) -> str:
    """
    Transcribe an audio recording that has been uploaded to the Gemini Files API.
    file_uri: "uri" returned by upload_file_to_gemini.
    Returns plain text transcript.
    Use this standalone if you only need the transcript, or before summarize_meeting
    if you want to inspect the transcript before generating a summary.
    """
    if not file_uri:
        raise ValueError("file_uri cannot be empty.")

    client = _make_client()
    gemini_file = get_gemini_file(client, file_uri)

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            gemini_file,
            "Transcribe this audio recording verbatim. Return only the plain text transcript with no commentary, labels, or formatting.",
        ],
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low")
        ),
    )

    transcript = response.text.strip()
    if not transcript:
        raise ValueError(
            "No transcript could be extracted from the audio. "
            "The recording may be silent, corrupted, or in an unsupported format."
        )
    return transcript


@mcp.tool()
def summarize_meeting(transcript: str) -> dict:
    """
    Generate an institutional-grade meeting summary from a transcript.
    Strictly grounded — only what is explicitly stated in the transcript is reported.
    Returns: { "summary": str, "context": str }
    The context field is the same summary, formatted for use as input to chat_with_meeting.
    Use chat_with_meeting afterwards for follow-up Q&A against the meeting content.
    """
    if not transcript or not transcript.strip():
        raise ValueError("transcript cannot be empty.")

    client = _make_client()

    response = client.models.generate_content(
        model=MODEL,
        contents=[SUMMARY_PROMPT, f"TRANSCRIPT:\n\n{transcript}"],
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low")
        ),
    )

    summary = response.text
    return {"summary": summary, "context": summary}


@mcp.tool()
def process_meeting_audio(file_uri: str) -> dict:
    """
    Transcribe an audio recording and generate a structured meeting summary.
    file_uri: "uri" returned by upload_file_to_gemini.
    Returns: { "summary": str, "context": str }
    Pass the context value to chat_with_meeting for follow-up questions.
    """
    transcript = transcribe_audio(file_uri)
    return summarize_meeting(transcript)


@mcp.tool()
def chat_with_meeting(context: str, question: str, history: list[dict] = None) -> str:
    """
    Ask a follow-up question about a meeting that has already been summarised.
    context: the context value returned by process_meeting_audio or summarize_meeting.
    question: the question to answer.
    history: optional list of prior Q&A turns as [{"role": "user"|"assistant", "content": str}].
    Returns a grounded answer drawn strictly from the meeting content.
    """
    if not context or not context.strip():
        raise ValueError("context cannot be empty.")
    if not question or not question.strip():
        raise ValueError("question cannot be empty.")

    client = _make_client()

    system_turn = (
        f"You are analyzing a meeting. "
        f"Answer questions based only on the following meeting summary. "
        f"Do not speculate or add information not present in the summary.\n\n"
        f"MEETING SUMMARY:\n\n{context}"
    )

    contents = [system_turn]

    for turn in (history or []):
        role = "model" if turn.get("role") == "assistant" else turn.get("role", "user")
        contents.append({"role": role, "parts": [{"text": turn["content"]}]})

    contents.append({"role": "user", "parts": [{"text": question}]})

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="low")
        ),
    )

    return response.text
