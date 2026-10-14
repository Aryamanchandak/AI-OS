from __future__ import annotations

import os
import time

from google import genai
from google.genai import types


def gemini_api_key() -> str:
    """Return the configured Gemini API key or raise a clear runtime error."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "Set GEMINI_API_KEY or GOOGLE_API_KEY to use Gemini tools."
        )
    return key


def make_gemini_client() -> genai.Client:
    """Create a Gemini client using the repo's supported API key environment names."""
    return genai.Client(api_key=gemini_api_key())


def gemini_file_name(file_ref: str) -> str:
    """
    Normalize a Gemini file reference into the API name form, ``files/...``.

    Accepts the Files API URI returned by upload_file_to_gemini, an existing
    ``files/...`` name, or a bare file id.
    """
    if not file_ref or not file_ref.strip():
        raise ValueError("Gemini file reference cannot be empty.")

    ref = file_ref.strip()
    if "/files/" in ref:
        file_id = ref.rsplit("/files/", 1)[-1]
    elif ref.startswith("files/"):
        file_id = ref.removeprefix("files/")
    else:
        file_id = ref

    file_id = file_id.strip("/")
    if not file_id:
        raise ValueError(f"Invalid Gemini file reference: {file_ref!r}")
    return f"files/{file_id}"


def get_gemini_file(client: genai.Client, file_ref: str):
    """Look up an already-uploaded Gemini Files API file by URI, name, or id."""
    return client.files.get(name=gemini_file_name(file_ref))


def wait_for_gemini_file_active(
    client: genai.Client,
    gemini_file,
    *,
    poll_seconds: float = 1.0,
):
    """Poll Gemini until an uploaded Files API file is ACTIVE."""
    while gemini_file.state.name != "ACTIVE":
        time.sleep(poll_seconds)
        gemini_file = client.files.get(name=gemini_file.name)
    return gemini_file


def pdf_bytes_part(pdf_bytes: bytes) -> types.Part:
    """
    Build an inline Gemini PDF part from raw PDF bytes.

    Use this only for workflows that intentionally send a PDF directly in the
    model request instead of uploading through the Gemini Files API.
    """
    if not pdf_bytes:
        raise ValueError("pdf_bytes cannot be empty.")
    return types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
