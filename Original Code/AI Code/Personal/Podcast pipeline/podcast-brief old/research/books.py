"""
research/books.py — Look up books and historical figures for biography/founder podcasts.
Uses Google Books (key optional) and Wikipedia (free).
"""

import os
import time
import requests
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class BookResult:
    title: str
    authors: list[str]
    year: Optional[int]
    description: str
    url: str
    source: str   # "google_books"


@dataclass
class WikiResult:
    title: str
    extract: str
    url: str


@dataclass
class HistoricalFinding:
    claim_summary: str
    claim_quote: str
    claim_speaker: str
    claim_timestamp: str
    books: list[BookResult]
    wiki: Optional[WikiResult]
    note: str   # one-line context

    def to_dict(self) -> dict:
        return {
            "claim_summary": self.claim_summary,
            "claim_quote": self.claim_quote,
            "claim_speaker": self.claim_speaker,
            "claim_timestamp": self.claim_timestamp,
            "books": [asdict(b) for b in self.books],
            "wiki": asdict(self.wiki) if self.wiki else None,
            "note": self.note,
        }


# ─── Google Books ────────────────────────────────────────────────────────────

def search_google_books(query: str, limit: int = 3) -> list[BookResult]:
    """Search Google Books. API key optional but raises rate limit."""
    params = {"q": query, "maxResults": limit}
    api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
    if api_key:
        params["key"] = api_key

    try:
        resp = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    books = []
    for item in data.get("items", []):
        info = item.get("volumeInfo", {})
        title = info.get("title", "")
        if not title:
            continue

        year = None
        published_date = info.get("publishedDate", "")
        if published_date and len(published_date) >= 4:
            try:
                year = int(published_date[:4])
            except ValueError:
                pass

        url = info.get("infoLink") or info.get("previewLink") or ""

        books.append(BookResult(
            title=title,
            authors=info.get("authors", [])[:3],
            year=year,
            description=(info.get("description") or "")[:500],
            url=url,
            source="google_books",
        ))

    return books


# ─── Wikipedia ───────────────────────────────────────────────────────────────

def search_wikipedia(query: str) -> Optional[WikiResult]:
    """Look up a topic on Wikipedia and return the lead extract."""
    try:
        # Step 1: search for the most relevant page
        search_resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 1,
            },
            timeout=10,
            headers={"User-Agent": "podcast-brief/0.1"},
        )
        search_resp.raise_for_status()
        results = search_resp.json().get("query", {}).get("search", [])
        if not results:
            return None

        page_title = results[0]["title"]

        # Step 2: fetch the lead summary
        summary_resp = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{page_title.replace(' ', '_')}",
            timeout=10,
            headers={"User-Agent": "podcast-brief/0.1"},
        )
        if summary_resp.status_code != 200:
            return None

        data = summary_resp.json()
        extract = data.get("extract", "")
        if not extract:
            return None

        return WikiResult(
            title=data.get("title", page_title),
            extract=extract[:800],
            url=data.get("content_urls", {}).get("desktop", {}).get("page", "")
                or f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}",
        )
    except Exception:
        return None


# ─── Research over a list of claims ──────────────────────────────────────────

def research_book_claims(claims: list, max_claims: int = 15) -> list[HistoricalFinding]:
    """
    For book references and historical claims, look up books and Wikipedia entries.
    Lighter touch than academic/news — biographical podcasts are usually well-sourced
    by the host already; this layer just adds links and quick context.
    """
    relevant_types = {"book_reference", "historical"}
    relevant = [c for c in claims if c.type in relevant_types][:max_claims]

    findings = []
    for claim in relevant:
        time.sleep(0.3)

        books = []
        wiki = None
        note = ""

        if claim.type == "book_reference":
            books = search_google_books(claim.search_query, limit=3)
            if books:
                note = f"Top match: {books[0].title}"
                if books[0].authors:
                    note += f" by {books[0].authors[0]}"
                if books[0].year:
                    note += f" ({books[0].year})"
            else:
                note = "No direct book match found."

        elif claim.type == "historical":
            wiki = search_wikipedia(claim.search_query)
            if wiki:
                note = f"Wikipedia: {wiki.title}"
            else:
                note = "No Wikipedia entry found for this query."

        findings.append(HistoricalFinding(
            claim_summary=claim.summary,
            claim_quote=claim.quote,
            claim_speaker=claim.speaker,
            claim_timestamp=claim.timestamp,
            books=books,
            wiki=wiki,
            note=note,
        ))

    return findings
