"""
Web search via Brave Search.

The calling agent chooses max_results based on query complexity; this tool only
validates the requested count and executes the search.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

import usage as _usage
from tool_registry import register

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_SEARCH_RESULTS = 20


def _ai_code_root() -> Path:
    env_root = os.environ.get("AI_CODE_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def _root_env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip()

    env_path = _ai_code_root() / ".env"
    if not env_path.exists():
        return None

    for line in env_path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, raw_value = clean.split("=", 1)
        if key.strip() == name:
            return raw_value.strip().strip('"').strip("'")
    return None


def _brave_api_key() -> str:
    key = _root_env_value("BRAVE_SEARCH_API_KEY")
    if not key:
        raise RuntimeError(
            "Set BRAVE_SEARCH_API_KEY in the AI Code root .env file to use web_search."
        )
    return key


def _brave_search(query: str, max_results: int) -> list[dict]:
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": _brave_api_key(),
    }
    params = {
        "q": query,
        "count": max_results,
    }
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(BRAVE_SEARCH_URL, headers=headers, params=params)
        response.raise_for_status()

    data = response.json()
    results = (data.get("web") or {}).get("results") or []
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
            "source": "brave",
        }
        for item in results[:max_results]
        if item.get("url")
    ]


@register(group="utility")
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web with Brave Search.

    Pass a concise search-engine query, not a chatty prompt. Use keywords plus
    context: entity/topic, important nouns, timeframe, document/event, or metric.
    For broad research, run multiple focused searches instead of one giant query.
    The caller chooses max_results based on query complexity.
    """
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query cannot be empty.")

    result_count = max(1, min(int(max_results), MAX_SEARCH_RESULTS))
    results = _brave_search(clean_query, result_count)
    _usage.bump("brave_search")
    return results
