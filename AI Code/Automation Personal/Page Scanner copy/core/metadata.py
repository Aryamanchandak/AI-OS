"""Book metadata resolution for the drop-folder ingest.

You type a book title (as a folder name, or in a book.txt inside the folder) and
this resolves it to real bibliographic metadata — canonical title, author(s),
year, ISBN, subjects — so every highlight lands in the Raw Data lake tagged with
identity that other automations can key on. Metadata matters, so:

  * Open Library is primary (free, no key); Google Books is the fallback.
  * The result is cached to `<folder>/.book.json`. It is fetched ONCE; you can
    open that file and correct any field by hand — the cache always wins on the
    next run, so a manual fix is never overwritten.
  * A low-confidence match (returned, but the title doesn't really match what you
    typed) is flagged so the cockpit can ask you to confirm it.
  * Offline / no-hit degrades gracefully to a title-only record — the scan still
    runs, it just carries less metadata.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

CACHE_NAME = ".book.json"
QUERY_FILE = "book.txt"
_TIMEOUT = 8            # seconds; a hung lookup must not stall the whole batch
_MAX_SUBJECTS = 8


def _norm(s: str) -> str:
    """Lowercased, punctuation-stripped, whitespace-collapsed — for match scoring."""
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return " ".join(s.split())


def _get_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "page-scanner/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _confidence(query: str, title: str | None) -> str:
    """How well the resolved title matches what you typed. The query may include
    an author ('Atomic Habits, James Clear'), so a title contained in the query
    (or vice-versa) counts as exact."""
    if not title:
        return "none"
    q, t = _norm(query), _norm(title)
    if not t:
        return "none"
    if t in q or q in t:
        return "exact"
    overlap = len(set(q.split()) & set(t.split()))
    return "fuzzy" if overlap >= 2 else "low"


def _blank(query: str) -> dict:
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


def _from_openlibrary(query: str) -> dict | None:
    url = (
        "https://openlibrary.org/search.json?"
        + urllib.parse.urlencode(
            {
                "q": query,
                "limit": 1,
                "fields": "title,author_name,first_publish_year,isbn,subject,cover_i",
            }
        )
    )
    data = _get_json(url)
    if not data or not data.get("docs"):
        return None
    d = data["docs"][0]
    title = d.get("title")
    return {
        "title": title,
        "author": ", ".join(d.get("author_name", [])) or None,
        "year": d.get("first_publish_year"),
        "isbn": (d.get("isbn") or [None])[0],
        "subjects": [s for s in (d.get("subject") or [])][:_MAX_SUBJECTS],
        "cover_url": (
            f"https://covers.openlibrary.org/b/id/{d['cover_i']}-M.jpg"
            if d.get("cover_i") else None
        ),
        "meta_source": "openlibrary",
        "confidence": _confidence(query, title),
        "query": query.strip(),
    }


def _from_google_books(query: str) -> dict | None:
    url = (
        "https://www.googleapis.com/books/v1/volumes?"
        + urllib.parse.urlencode({"q": query, "maxResults": 1})
    )
    data = _get_json(url)
    if not data or not data.get("items"):
        return None
    v = data["items"][0].get("volumeInfo", {})
    title = v.get("title")
    isbn = None
    for ident in v.get("industryIdentifiers", []):
        if ident.get("type", "").startswith("ISBN"):
            isbn = ident.get("identifier")
            if ident.get("type") == "ISBN_13":
                break
    year = None
    if v.get("publishedDate"):
        m = re.match(r"(\d{4})", v["publishedDate"])
        year = int(m.group(1)) if m else None
    return {
        "title": title,
        "author": ", ".join(v.get("authors", [])) or None,
        "year": year,
        "isbn": isbn,
        "subjects": [s for s in (v.get("categories") or [])][:_MAX_SUBJECTS],
        "cover_url": (v.get("imageLinks") or {}).get("thumbnail"),
        "meta_source": "google_books",
        "confidence": _confidence(query, title),
        "query": query.strip(),
    }


def resolve_book(query: str) -> dict:
    """Look up a free-text book title. Never raises — worst case is a title-only
    record with confidence='none' (offline or no hit)."""
    query = (query or "").strip()
    if not query:
        return _blank("")
    for fetch in (_from_openlibrary, _from_google_books):
        result = fetch(query)
        if result and result.get("title"):
            return result
    return _blank(query)


def _query_from_folder(folder: Path) -> str:
    """The title to resolve: first non-empty line of book.txt, else folder name."""
    txt = folder / QUERY_FILE
    if txt.exists():
        for line in txt.read_text(encoding="utf-8").splitlines():
            if line.strip():
                return line.strip()
    return folder.name.strip()


def load_or_resolve(folder: Path) -> dict:
    """Return this book folder's metadata, resolving + caching on first sight.

    A pre-existing .book.json always wins (so hand-edits stick); it is only
    written when absent.
    """
    cache = folder / CACHE_NAME
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if cached.get("title"):
                return cached
        except Exception:
            pass                      # corrupt cache → fall through and re-resolve

    meta = resolve_book(_query_from_folder(folder))
    try:
        cache.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass                          # read-only folder shouldn't kill the scan
    return meta
