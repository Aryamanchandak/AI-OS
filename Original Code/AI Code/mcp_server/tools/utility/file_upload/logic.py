from sandbox import _safe
from shared.backend_utils import make_gemini_client, wait_for_gemini_file_active


def upload_file_to_gemini(source: str) -> dict[str, str | None]:
    """
    Upload one sandbox file to the Gemini Files API and return reusable ids.

    Use this before calling tools that need an already-uploaded Gemini file,
    such as annual-report analysis, credit-note generation, or meeting audio
    transcription.

    source must be a filename or sandbox-relative path for a file that already
    exists in the server sandbox. Absolute local paths and HTTP/HTTPS URLs are
    not accepted. This tool uploads the file, waits until Gemini marks it
    ACTIVE, then returns both identifiers Gemini exposes:

    - name: the Gemini Files API name, e.g. "files/abc123"
    - uri: the Gemini Files API URI to pass to downstream tools as file_uri

    Returns:
    {
      "name": "files/...",
      "uri": "https://generativelanguage.googleapis.com/...",
      "mime_type": "...",
      "display_name": "..."
    }
    """
    if not source:
        raise ValueError("source cannot be empty.")
    if source.startswith(("http://", "https://")):
        raise ValueError(
            "HTTP/HTTPS URLs are not supported. Upload a file already present "
            "in the server sandbox."
        )

    resolved = _safe(source)  # raises ValueError if path escapes sandbox

    if not resolved.exists():
        raise FileNotFoundError(f"File not found in sandbox: {source!r}")
    if not resolved.is_file():
        raise ValueError(f"Source must be a file in the sandbox: {source!r}")

    client = make_gemini_client()
    gemini_file = client.files.upload(file=str(resolved))
    gemini_file = wait_for_gemini_file_active(client, gemini_file)

    return {
        "name": gemini_file.name,
        "uri": gemini_file.uri,
        "mime_type": getattr(gemini_file, "mime_type", None),
        "display_name": getattr(gemini_file, "display_name", None),
    }
