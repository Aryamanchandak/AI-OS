from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
from urllib import parse, request
from uuid import uuid4
import xml.etree.ElementTree as ET

from .schema import Source


@dataclass(slots=True)
class Ingested:
    text: str
    source: Source


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def from_text(text: str, title: str = "", locator: str = "pasted-text") -> Ingested:
    return Ingested(text=text, source=Source(str(uuid4()), "text", locator, title))


def from_path(path_value: str | Path) -> Ingested:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Input is not a file: {path}")
    suffix = path.suffix.casefold()
    if suffix in {".txt", ".md", ".markdown"}:
        text = path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF support requires: pip install 'model-forge[pdf]'") from exc
        text = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    elif suffix in {".mp3", ".wav", ".m4a", ".webm", ".mp4"}:
        text = _transcribe(path)
    else:
        raise ValueError(f"Unsupported file type {suffix}; use TXT, Markdown, PDF, or audio")
    return Ingested(text, Source(str(uuid4()), suffix.lstrip("."), str(path), path.stem))


def from_upload(filename: str, data: bytes) -> Ingested:
    """Ingest a browser upload without trusting or persisting its client path."""
    suffix = Path(filename).suffix.casefold()
    if suffix not in {".txt", ".md", ".markdown", ".pdf", ".mp3", ".wav", ".m4a", ".webm", ".mp4"}:
        raise ValueError("Unsupported upload; use TXT, Markdown, PDF, MP3, WAV, M4A, WEBM, or MP4")
    if len(data) > 25_000_000:
        raise ValueError("Upload exceeds the 25 MB limit")
    temporary = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    path = Path(temporary.name)
    try:
        temporary.write(data); temporary.close()
        ingested = from_path(path)
        ingested.source.locator = f"upload:{Path(filename).name}"
        ingested.source.title = Path(filename).stem
        return ingested
    finally:
        temporary.close()
        path.unlink(missing_ok=True)


def _transcribe(path: Path) -> str:
    import os
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Audio transcription requires OPENAI_API_KEY")
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("Audio support requires: pip install 'model-forge[audio]'") from exc
    with path.open("rb") as handle:
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (path.name, handle)}, data={"model": "gpt-4o-mini-transcribe"}, timeout=180,
        )
    if not response.ok:
        raise RuntimeError(f"Transcription failed ({response.status_code}): {response.text[:400]}")
    return response.json()["text"]


def from_url(url: str) -> Ingested:
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    req = request.Request(url, headers={"User-Agent": "ModelForge/0.1 (+local research tool)"})
    with request.urlopen(req, timeout=30) as response:
        content_type = response.headers.get_content_type()
        raw = response.read(5_000_000)
    if content_type == "application/pdf" or parsed.path.casefold().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            from io import BytesIO
        except ImportError as exc:
            raise RuntimeError("PDF URL support requires: pip install 'model-forge[pdf]'") from exc
        text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(raw)).pages)
    else:
        parser = _VisibleText()
        parser.feed(raw.decode("utf-8", errors="replace"))
        text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    return Ingested(text, Source(str(uuid4()), "url", url, parsed.netloc))


def live_news(query: str, limit: int = 10) -> Ingested:
    url = "https://news.google.com/rss/search?" + parse.urlencode({"q": query, "hl": "en", "gl": "US", "ceid": "US:en"})
    req = request.Request(url, headers={"User-Agent": "ModelForge/0.1"})
    with request.urlopen(req, timeout=30) as response:
        root = ET.fromstring(response.read())
    entries: list[str] = []
    for item in root.findall("./channel/item")[:limit]:
        title = item.findtext("title", "")
        description = re.sub(r"<[^>]+>", " ", item.findtext("description", ""))
        published = item.findtext("pubDate", "")
        try:
            published = parsedate_to_datetime(published).date().isoformat()
        except (TypeError, ValueError):
            pass
        entries.append(f"{published}: {title}. {description}")
    if not entries:
        raise RuntimeError(f"No live news found for {query!r}")
    return Ingested("\n".join(entries), Source(str(uuid4()), "live-news", url, f"News: {query}"))
