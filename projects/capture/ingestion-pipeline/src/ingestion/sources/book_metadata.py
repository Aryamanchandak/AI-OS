"""Book metadata lookup, caching, confirmation, and folder finalization."""

from __future__ import annotations

import base64
from datetime import datetime
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Literal, Protocol

from PIL import Image
from pydantic import BaseModel, ConfigDict

from ingestion.sources.page_scanner import store


CACHE_NAME = ".book.json"
QUERY_FILE = "book.txt"
_TIMEOUT = 8
_MAX_SUBJECTS = 8
COVER_CLASSIFICATION_PROFILE = "cover-classification-v1"
COVER_CLASSIFICATION_PROMPT = (
    "Determine whether this photograph shows the front cover of a book. If it "
    "does, read the book title and author directly from the cover. Ignore blurbs, "
    "publisher names, awards, and series banners. Return the requested structured "
    "fields; use null for title and author when this is not a book cover."
)
_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_EXIF_CAPTURE_TAGS = (36867, 36868, 306)  # original, digitized, generic datetime


class ChatClient(Protocol):
    def chat(
        self,
        prompt: str | None = None,
        *,
        messages: list[dict[str, Any]] | None = None,
        system: Any = None,
        profile: str | None = None,
        provider: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        response_format: Any = None,
    ) -> dict[str, Any]: ...


class CoverReadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_cover: bool
    title: str | None = None
    author: str | None = None


GateStatus = Literal["needs_cover", "needs_confirm", "clear"]


def _norm(s: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace for scoring."""

    s = re.sub(r"[^\w\s]", " ", s.lower())
    return " ".join(s.split())


def _get_json(url: str) -> dict[str, Any] | None:
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "page-scanner/1.0"}
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            value = json.loads(response.read().decode("utf-8"))
            return value if isinstance(value, dict) else None
    except Exception:
        return None


def _confidence(query: str, title: str | None) -> str:
    """Score how closely a resolved title matches the supplied query."""

    if not title:
        return "none"
    normalized_query, normalized_title = _norm(query), _norm(title)
    if not normalized_title:
        return "none"
    if normalized_title in normalized_query or normalized_query in normalized_title:
        return "exact"
    overlap = len(set(normalized_query.split()) & set(normalized_title.split()))
    return "fuzzy" if overlap >= 2 else "low"


def _blank(query: str) -> dict[str, Any]:
    return {
        "title": query.strip(),
        "author": None,
        "year": None,
        "isbn": None,
        "subjects": [],
        "cover_url": None,
        "meta_source": "none",
        "confidence": "none",
        "query": query.strip(),
    }


def _from_openlibrary(query: str) -> dict[str, Any] | None:
    url = (
        "https://openlibrary.org/search.json?"
        + urllib.parse.urlencode(
            {
                "q": query,
                "limit": 1,
                "fields": (
                    "title,author_name,first_publish_year,isbn,subject,cover_i"
                ),
            }
        )
    )
    data = _get_json(url)
    if not data or not data.get("docs"):
        return None
    document = data["docs"][0]
    title = document.get("title")
    return {
        "title": title,
        "author": ", ".join(document.get("author_name", [])) or None,
        "year": document.get("first_publish_year"),
        "isbn": (document.get("isbn") or [None])[0],
        "subjects": [
            subject for subject in (document.get("subject") or [])
        ][:_MAX_SUBJECTS],
        "cover_url": (
            f"https://covers.openlibrary.org/b/id/{document['cover_i']}-M.jpg"
            if document.get("cover_i")
            else None
        ),
        "meta_source": "openlibrary",
        "confidence": _confidence(query, title),
        "query": query.strip(),
    }


def _from_google_books(query: str) -> dict[str, Any] | None:
    url = (
        "https://www.googleapis.com/books/v1/volumes?"
        + urllib.parse.urlencode({"q": query, "maxResults": 1})
    )
    data = _get_json(url)
    if not data or not data.get("items"):
        return None
    volume = data["items"][0].get("volumeInfo", {})
    title = volume.get("title")
    isbn = None
    for identifier in volume.get("industryIdentifiers", []):
        if identifier.get("type", "").startswith("ISBN"):
            isbn = identifier.get("identifier")
            if identifier.get("type") == "ISBN_13":
                break
    year = None
    if volume.get("publishedDate"):
        match = re.match(r"(\d{4})", volume["publishedDate"])
        year = int(match.group(1)) if match else None
    return {
        "title": title,
        "author": ", ".join(volume.get("authors", [])) or None,
        "year": year,
        "isbn": isbn,
        "subjects": [
            category for category in (volume.get("categories") or [])
        ][:_MAX_SUBJECTS],
        "cover_url": (volume.get("imageLinks") or {}).get("thumbnail"),
        "meta_source": "google_books",
        "confidence": _confidence(query, title),
        "query": query.strip(),
    }


def resolve_book(query: str) -> dict[str, Any]:
    """Resolve a free-text title without raising on lookup failures."""

    query = (query or "").strip()
    if not query:
        return _blank("")
    for fetch in (_from_openlibrary, _from_google_books):
        result = fetch(query)
        if result and result.get("title"):
            return result
    return _blank(query)


def _query_from_book_txt(folder: Path) -> str | None:
    query_path = folder / QUERY_FILE
    if not query_path.exists():
        return None
    for line in query_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return line.strip()
    return None


def _read_cache(folder: Path) -> dict[str, Any] | None:
    cache_path = folder / CACHE_NAME
    if not cache_path.exists():
        return None
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return cached if isinstance(cached, dict) and cached.get("title") else None


def _write_cache(folder: Path, metadata: dict[str, Any]) -> None:
    try:
        (folder / CACHE_NAME).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _needs_cover(folder: Path) -> dict[str, Any]:
    return {
        "title": None,
        "author": None,
        "year": None,
        "isbn": None,
        "subjects": [],
        "cover_url": None,
        "meta_source": "needs_cover",
        "confidence": "none",
        "query": None,
        "folder": str(folder),
    }


def _image_content_block(photo: Path) -> dict[str, str]:
    """Build the gateway's canonical base64 image block for a local photo."""

    photo = Path(photo)
    try:
        media_type = _IMAGE_MEDIA_TYPES[photo.suffix.casefold()]
    except KeyError as exc:
        suffix = photo.suffix or "<none>"
        raise ValueError(f"unsupported cover image type: {suffix}") from exc
    return {
        "type": "image",
        "media_type": media_type,
        "data": base64.b64encode(photo.read_bytes()).decode("ascii"),
    }


def _classify_page(
    photo: Path, *, chat_client: ChatClient | None = None
) -> CoverReadResult:
    """Classify and read one photo through the gateway's local-only profile."""

    if chat_client is None:
        return CoverReadResult(is_cover=False)
    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": COVER_CLASSIFICATION_PROMPT},
                    _image_content_block(Path(photo)),
                ],
            }
        ]
        response = chat_client.chat(
            messages=messages,
            profile=COVER_CLASSIFICATION_PROFILE,
            response_format={
                "type": "json_schema",
                "schema": CoverReadResult.model_json_schema(),
            },
        )
        return CoverReadResult.model_validate(response["parsed"])
    except Exception:
        # A local-model failure must never fall through to a cloud provider or
        # cause an interior page to be filed as a cover.
        return CoverReadResult(is_cover=False)


def _capture_time(photo: Path) -> tuple[float, str]:
    """Return EXIF capture time, falling back to mtime for untagged images."""

    try:
        with Image.open(photo) as image:
            exif = image.getexif()
            for tag in _EXIF_CAPTURE_TAGS:
                raw_value = exif.get(tag)
                if raw_value:
                    value = str(raw_value).strip()
                    captured = datetime.strptime(value[:19], "%Y:%m:%d %H:%M:%S")
                    return captured.timestamp(), str(photo)
    except Exception:
        pass
    try:
        return photo.stat().st_mtime, str(photo)
    except OSError:
        return float("inf"), str(photo)


def find_cover(
    folder: Path, *, chat_client: ChatClient | None = None
) -> CoverReadResult | None:
    """Return the first EXIF-ordered, non-retake photo classified as a cover."""

    folder = Path(folder)
    candidates = (
        path
        for path in folder.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in _IMAGE_MEDIA_TYPES
        and "_retake" not in path.relative_to(folder).parts
    )
    for photo in sorted(candidates, key=_capture_time):
        result = _classify_page(photo, chat_client=chat_client)
        if result.is_cover:
            return result
    return None


def load_or_resolve(
    folder: Path, *, chat_client: ChatClient | None = None
) -> dict[str, Any]:
    """Load cached metadata or resolve the explicit/folder-derived book name."""

    folder = Path(folder)
    cached = _read_cache(folder)
    if cached is not None:
        return cached

    query = _query_from_book_txt(folder)
    if query is None:
        query = " ".join(folder.name.replace("_", " ").replace("-", " ").split())
        if not query:
            return _needs_cover(folder)

    metadata = resolve_book(query)
    metadata["confirmed"] = metadata.get("confidence") == "exact"
    _write_cache(folder, metadata)
    return metadata


def gate_status(folder: Path) -> GateStatus:
    metadata = load_or_resolve(folder)
    if metadata.get("meta_source") == "needs_cover":
        return "needs_cover"
    # A corrected lookup is deliberately human-inspected even when the lookup
    # itself reports an exact match. Older cache files do not have this marker
    # and retain their existing behaviour.
    if metadata.get("confirmation_required") is True:
        return "needs_confirm"
    if metadata.get("confidence") == "exact" or metadata.get("confirmed"):
        return "clear"
    return "needs_confirm"


def slugify_title(title: str) -> str:
    """Return the canonical folder slug for a resolved book title."""

    slug = re.sub(r"[\W_]+", "-", title.casefold(), flags=re.UNICODE).strip("-")
    return slug or "untitled-book"


# Compatibility for callers written before Component 4 made this a public
# cross-module contract.
_slugify_title = slugify_title


def finalize_resolved_folder(
    folder: Path, *, db_path: str | Path
) -> Path:
    """Rename a settled book folder and keep stored image paths synchronized."""

    folder = Path(folder)
    metadata = _read_cache(folder)
    if metadata is None:
        raise ValueError(f"{folder} has no valid resolved metadata cache")
    if metadata.get("confirmation_required") is True:
        raise ValueError("book metadata still requires human confirmation")
    if metadata.get("confidence") != "exact" and not metadata.get("confirmed"):
        raise ValueError("book metadata must be exact or confirmed before rename")

    destination = folder.with_name(slugify_title(str(metadata["title"])))
    if destination == folder:
        return folder
    if destination.exists():
        raise FileExistsError(f"resolved book folder already exists: {destination}")

    folder.rename(destination)
    try:
        store.rewrite_image_paths_under_folder(
            db_path, old_folder=folder, new_folder=destination
        )
    except Exception:
        try:
            destination.rename(folder)
        except Exception as rollback_error:
            raise RuntimeError(
                "database path rewrite failed and the folder rename could not "
                "be rolled back"
            ) from rollback_error
        raise
    return destination


def record_correction(
    folder: Path, *, title: str, author: str | None, db_path: str | Path
) -> Path:
    """Re-resolve a human correction and persist it for later confirmation.

    A book whose real title carries a subtitle — `Sapiens Yuval Noah Harari`
    against `Sapiens: A Brief History of Humankind` — resolves with low
    confidence and stops for confirmation. Without this, the only way forward is
    to accept whatever the lookup returned, which then gets written into
    `.book.json`, into the folder name, and into every stored `pages.image_path`
    underneath it.
    """

    folder = Path(folder)
    title = (title or "").strip()
    if not title:
        raise ValueError("a corrected book title cannot be blank")
    del db_path  # Retained in the public signature for existing callers.
    typed_author = (author or "").strip() or None
    query = " ".join(value for value in (title, typed_author) if value)
    resolved = resolve_book(query)

    if resolved.get("title") and resolved.get("meta_source") not in {None, "none"}:
        # Normalize lookup-provider and test-double results into the complete
        # cache shape the review adapter can rely on.
        metadata = {
            "title": resolved.get("title"),
            "author": resolved.get("author"),
            "year": resolved.get("year"),
            "isbn": resolved.get("isbn"),
            "subjects": list(resolved.get("subjects") or []),
            "cover_url": resolved.get("cover_url"),
            "meta_source": resolved.get("meta_source"),
            "confidence": resolved.get("confidence") or "none",
            "query": resolved.get("query") or query,
        }
    else:
        # Offline/no-match remains human-authoritative without inventing
        # enrichment. It is still shown once more before being accepted.
        metadata = _blank(title)
        metadata.update(
            {
                "author": typed_author,
                "meta_source": "human_fallback",
                "query": query,
            }
        )

    metadata.update({"confirmed": False, "confirmation_required": True})
    _write_cache(folder, metadata)
    return folder


def record_confirmation(folder: Path, *, db_path: str | Path) -> Path:
    """Persist confirmation and finalize the folder's resolved identity."""

    folder = Path(folder)
    metadata = _read_cache(folder)
    if metadata is None:
        raise ValueError(f"{folder} has no valid resolved metadata cache")
    metadata["confirmed"] = True
    metadata["confirmation_required"] = False

    cache_path = folder / CACHE_NAME
    temporary = folder / f"{CACHE_NAME}.tmp"
    temporary.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(cache_path)
    return finalize_resolved_folder(folder, db_path=db_path)
