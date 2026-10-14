"""Narrow, read-only search tools for websites and academic research.

``website_search`` searches DuckDuckGo but returns results only from domains in
the local allowlist. It never opens result URLs. ``research_search`` calls one
fixed Semantic Scholar API endpoint and cannot be redirected by tool input.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from ..app import mcp

_DEFAULT_ALLOWLIST = Path(__file__).resolve().parents[1] / "allowed_websites.txt"
_SEMANTIC_SCHOLAR_SEARCH_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)
_PAPER_FIELDS = (
    "title,abstract,authors,year,publicationDate,citationCount,url,"
    "openAccessPdf,externalIds"
)


def _allowlist_path() -> Path:
    override = os.getenv("WEB_SEARCH_ALLOWED_DOMAINS_FILE", "").strip()
    return Path(override).expanduser() if override else _DEFAULT_ALLOWLIST


def _normalise_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if not domain:
        raise ValueError("domain cannot be empty")
    if "://" in domain or any(char in domain for char in "/\\?#@:"):
        raise ValueError(
            f"invalid domain {value!r}; use a hostname such as example.com"
        )
    if domain.startswith(".") or domain.endswith(".") or "." not in domain:
        raise ValueError(f"invalid public domain {value!r}")
    labels = domain.split(".")
    if any(
        not label
        or label.startswith("-")
        or label.endswith("-")
        or not all(char.isalnum() or char == "-" for char in label)
        for label in labels
    ):
        raise ValueError(f"invalid public domain {value!r}")
    return domain


def _load_allowed_domains() -> tuple[str, ...]:
    env_value = os.getenv("WEB_SEARCH_ALLOWED_DOMAINS", "").strip()
    if env_value:
        domains: list[str] = []
        for position, raw_value in enumerate(env_value.split(","), start=1):
            try:
                domain = _normalise_domain(raw_value)
            except ValueError as exc:
                raise RuntimeError(
                    f"WEB_SEARCH_ALLOWED_DOMAINS entry {position}: {exc}"
                ) from exc
            if domain not in domains:
                domains.append(domain)
        return tuple(domains)

    path = _allowlist_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise RuntimeError(f"website allowlist does not exist: {path}") from exc

    domains = []
    for line_number, raw_line in enumerate(lines, start=1):
        value = raw_line.split("#", 1)[0].strip()
        if not value:
            continue
        try:
            domain = _normalise_domain(value)
        except ValueError as exc:
            raise RuntimeError(f"{path}:{line_number}: {exc}") from exc
        if domain not in domains:
            domains.append(domain)
    return tuple(domains)


def _host_is_allowed(url: str, allowed_domains: tuple[str, ...]) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def _duckduckgo_text(query: str, max_results: int) -> list[dict[str, object]]:
    # Import lazily so MCP discovery can still report an actionable tool error if
    # dependencies were not synced after this tool was added.
    from ddgs import DDGS

    return list(
        DDGS(timeout=12).text(
            query,
            region="wt-wt",
            safesearch="moderate",
            max_results=max_results,
            backend="duckduckgo",
        )
    )


@mcp.tool()
def website_search(query: str, max_results: int = 5, site: str = "") -> str:
    """Search allowed public websites through DuckDuckGo.

    Returns titles, URLs, and short search-result snippets only. It does not open,
    scrape, or download from result URLs. Results are restricted to the domains in
    ``simple_server/allowed_websites.txt``. ``site`` may narrow the search to one
    configured domain but cannot expand the allowlist.
    """
    query = query.strip()
    if not query:
        return "ERROR: query cannot be empty"
    max_results = max(1, min(max_results, 10))

    try:
        allowed_domains = _load_allowed_domains()
    except Exception as exc:  # noqa: BLE001 - return a useful MCP observation
        return f"ERROR: could not load website allowlist: {exc}"
    if not allowed_domains:
        return (
            "ERROR: website search is disabled because the allowlist is empty. "
            "Set WEB_SEARCH_ALLOWED_DOMAINS in .env or add one domain per line "
            f"to {_allowlist_path()}"
        )

    selected_domains = allowed_domains
    if site.strip():
        try:
            requested_site = _normalise_domain(site)
        except ValueError as exc:
            return f"ERROR: invalid site: {exc}"
        if requested_site not in allowed_domains:
            return f"ERROR: site {requested_site!r} is not in the website allowlist"
        selected_domains = (requested_site,)

    domain_query = " OR ".join(f"site:{domain}" for domain in selected_domains)
    restricted_query = f"({domain_query}) {query}"
    candidate_limit = min(max(max_results * 4, 10), 40)

    try:
        candidates = _duckduckgo_text(restricted_query, candidate_limit)
    except Exception as exc:  # noqa: BLE001 - provider failures are observations
        return f"ERROR: DuckDuckGo search failed: {type(exc).__name__}: {exc}"

    results: list[dict[str, str]] = []
    for item in candidates:
        url = str(item.get("href") or item.get("url") or "").strip()
        if not _host_is_allowed(url, selected_domains):
            continue
        results.append(
            {
                "title": str(item.get("title") or "").strip(),
                "url": url,
                "snippet": str(item.get("body") or item.get("snippet") or "").strip()[:1000],
            }
        )
        if len(results) >= max_results:
            break

    return json.dumps(
        {
            "provider": "duckduckgo",
            "allowed_domains": list(selected_domains),
            "results": results,
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def research_search(
    query: str,
    max_results: int = 5,
    year_from: int | None = None,
    open_access_only: bool = False,
) -> str:
    """Search academic papers through Semantic Scholar's fixed public API.

    Returns paper metadata, abstracts, citation counts, canonical links, and
    open-access PDF links when Semantic Scholar supplies them. This tool cannot
    fetch arbitrary URLs or download papers.
    """
    query = query.strip()
    if not query:
        return "ERROR: query cannot be empty"
    max_results = max(1, min(max_results, 10))
    if year_from is not None and not 1900 <= year_from <= 2100:
        return "ERROR: year_from must be between 1900 and 2100"

    params: dict[str, str | int] = {
        "query": query,
        "limit": max_results,
        "fields": _PAPER_FIELDS,
    }
    if year_from is not None:
        params["publicationDateOrYear"] = f"{year_from}:"
    if open_access_only:
        params["openAccessPdf"] = ""

    headers = {"Accept": "application/json"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    try:
        response = httpx.get(
            _SEMANTIC_SCHOLAR_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=20,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - provider failures are observations
        return f"ERROR: Semantic Scholar search failed: {type(exc).__name__}: {exc}"

    papers: list[dict[str, object]] = []
    for item in payload.get("data", [])[:max_results]:
        authors = [
            str(author.get("name", ""))
            for author in item.get("authors") or []
            if author.get("name")
        ]
        open_access = item.get("openAccessPdf") or {}
        papers.append(
            {
                "title": item.get("title"),
                "authors": authors,
                "year": item.get("year"),
                "publication_date": item.get("publicationDate"),
                "abstract": str(item.get("abstract") or "")[:4000] or None,
                "citation_count": item.get("citationCount"),
                "url": item.get("url"),
                "open_access_pdf": open_access.get("url"),
                "external_ids": item.get("externalIds") or {},
            }
        )

    return json.dumps(
        {"provider": "semantic_scholar", "results": papers},
        indent=2,
        ensure_ascii=False,
    )
