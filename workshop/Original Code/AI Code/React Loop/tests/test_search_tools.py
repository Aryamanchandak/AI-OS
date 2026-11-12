"""Safety and behavior tests for the two read-only search tools."""

from __future__ import annotations

import json

from simple_server.tools import search


def _write_allowlist(monkeypatch, tmp_path, contents: str):
    path = tmp_path / "allowed_websites.txt"
    path.write_text(contents, encoding="utf-8")
    monkeypatch.delenv("WEB_SEARCH_ALLOWED_DOMAINS", raising=False)
    monkeypatch.setenv("WEB_SEARCH_ALLOWED_DOMAINS_FILE", str(path))
    return path


def test_website_search_fails_closed_with_empty_allowlist(monkeypatch, tmp_path):
    _write_allowlist(monkeypatch, tmp_path, "# no enabled domains\n")
    monkeypatch.setattr(
        search,
        "_duckduckgo_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("called")),
    )

    result = search.website_search("safe query")

    assert result.startswith("ERROR:")
    assert "allowlist is empty" in result


def test_website_search_filters_unlisted_domains(monkeypatch, tmp_path):
    _write_allowlist(monkeypatch, tmp_path, "example.com\n")
    monkeypatch.setattr(
        search,
        "_duckduckgo_text",
        lambda _query, _limit: [
            {"title": "Allowed", "href": "https://docs.example.com/page", "body": "ok"},
            {"title": "Blocked", "href": "https://evil.example/page", "body": "no"},
            {"title": "Lookalike", "href": "https://example.com.evil.test/", "body": "no"},
        ],
    )

    payload = json.loads(search.website_search("documentation"))

    assert [item["title"] for item in payload["results"]] == ["Allowed"]
    assert payload["allowed_domains"] == ["example.com"]


def test_website_search_reads_comma_separated_env_allowlist(monkeypatch):
    monkeypatch.setenv(
        "WEB_SEARCH_ALLOWED_DOMAINS", "economist.com, bbc.com, bbc.co.uk"
    )
    monkeypatch.setattr(
        search,
        "_duckduckgo_text",
        lambda _query, _limit: [
            {
                "title": "BBC",
                "href": "https://www.bbc.com/news/articles/example",
                "body": "News",
            }
        ],
    )

    payload = json.loads(search.website_search("world news"))

    assert payload["allowed_domains"] == ["economist.com", "bbc.com", "bbc.co.uk"]
    assert payload["results"][0]["title"] == "BBC"


def test_website_search_site_cannot_expand_allowlist(monkeypatch, tmp_path):
    _write_allowlist(monkeypatch, tmp_path, "example.com\n")

    result = search.website_search("query", site="not-allowed.example")

    assert result.startswith("ERROR:")
    assert "not in the website allowlist" in result


def test_allowlist_rejects_urls_instead_of_domains(monkeypatch, tmp_path):
    path = _write_allowlist(monkeypatch, tmp_path, "https://example.com/page\n")

    result = search.website_search("query")

    assert result.startswith("ERROR:")
    assert f"{path}:1" in result
    assert "use a hostname" in result


def test_research_search_uses_fixed_endpoint(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "title": "A Paper",
                        "authors": [{"name": "Ada Researcher"}],
                        "year": 2025,
                        "publicationDate": "2025-01-02",
                        "abstract": "Findings",
                        "citationCount": 7,
                        "url": "https://www.semanticscholar.org/paper/id",
                        "openAccessPdf": {"url": "https://example.org/paper.pdf"},
                        "externalIds": {"DOI": "10.1/example"},
                    }
                ]
            }

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(search.httpx, "get", fake_get)

    payload = json.loads(
        search.research_search(
            "reliable agents", max_results=3, year_from=2020, open_access_only=True
        )
    )

    assert captured["url"] == search._SEMANTIC_SCHOLAR_SEARCH_URL
    assert captured["params"]["publicationDateOrYear"] == "2020:"
    assert "openAccessPdf" in captured["params"]
    assert payload["results"][0]["title"] == "A Paper"
    assert payload["results"][0]["authors"] == ["Ada Researcher"]
