import os
import time

from google import genai
from mcp.server.fastmcp import FastMCP

from sandbox import _safe

mcp = FastMCP("file-upload")


@mcp.tool()
def upload_file(file_path: str) -> str:
    """
    Upload a sandbox file to the Gemini Files API and return its URI.

    file_path must be a filename (or sandbox-relative path) for a file that
    already exists in the server's sandbox directory. Absolute paths are
    not accepted. Waits until the file reaches ACTIVE state before returning.
    The returned URI can be passed directly to analyze_annual_report,
    generate_credit_one_pager, generate_credit_section, generate_credit_note,
    transcribe_audio, or process_meeting_audio.
    """
    if not file_path:
        raise ValueError("file_path cannot be empty.")

    resolved = _safe(file_path)  # raises ValueError if path escapes sandbox

    if not resolved.exists():
        raise FileNotFoundError(f"File not found in sandbox: {file_path!r}")

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    gemini_file = client.files.upload(file=str(resolved))

    while gemini_file.state.name != "ACTIVE":
        time.sleep(1)
        gemini_file = client.files.get(name=gemini_file.name)

    return gemini_file.uri
