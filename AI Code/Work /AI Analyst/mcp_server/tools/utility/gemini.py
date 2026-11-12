"""
Gemini Files API upload with URL support.

Complements the existing `upload_file` tool (local paths only) by also
accepting HTTP/HTTPS URLs — it downloads the file into the sandbox first,
then uploads to Gemini. Both tools return a Gemini file URI.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse as _urlparse

import httpx

from tool_registry import register
from sandbox import SANDBOX, _safe


def _gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "Set GEMINI_API_KEY or GOOGLE_API_KEY to use the Gemini Files API."
        )
    return key


def _upload_local_to_gemini(path: Path) -> str:
    """Upload a local file to Gemini Files API. Blocks until ACTIVE. Returns URI."""
    from google import genai as _genai

    client = _genai.Client(api_key=_gemini_api_key())
    f = client.files.upload(file=str(path))
    while f.state.name != "ACTIVE":
        time.sleep(1)
        f = client.files.get(name=f.name)
    return f.uri


@register(group="utility")
def upload_to_gemini(source: str) -> str:
    """
    Upload a file to the Gemini Files API and return its URI.

    source: a sandbox-relative file path OR an HTTP/HTTPS URL.
    - URL sources are downloaded into the sandbox before uploading.
    - Relative paths are resolved inside the sandbox directory.
    The returned URI can be passed to analyze_annual_report,
    generate_credit_one_pager, transcribe_audio, or process_meeting_audio.

    Example: upload_to_gemini("reports/q4.pdf")
    Example: upload_to_gemini("https://example.com/report.pdf")
    """
    if source.startswith(("http://", "https://")):
        resp = httpx.get(source, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        cd = resp.headers.get("content-disposition", "")
        fname = None
        if "filename=" in cd:
            fname = cd.split("filename=")[-1].strip('" ')
        if not fname:
            fname = Path(_urlparse(source).path).name or "download"
        fname = Path(fname).name or "download"  # strip any path traversal components
        dest = _safe(fname)  # validates fname stays inside sandbox
        dest.write_bytes(resp.content)
        return _upload_local_to_gemini(dest)
    else:
        p = _safe(source)
        if not p.exists():
            raise FileNotFoundError(f"File not found in sandbox: {source}")
        return _upload_local_to_gemini(p)
