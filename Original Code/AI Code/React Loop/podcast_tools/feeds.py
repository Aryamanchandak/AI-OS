"""Curated podcast feeds: resolve a short name (or a raw URL) to an RSS URL.

Self-contained like the rest of ``podcast_tools`` — the feed list ships inside the
package (``feeds.txt`` next to this file) so the package stays portable. The path
is overridable with the ``PODCAST_FEEDS_FILE`` environment variable.
"""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

DEFAULT_FEEDS_FILE = Path(__file__).resolve().parent / "feeds.txt"


def _feeds_path() -> Path:
    override = os.getenv("PODCAST_FEEDS_FILE", "").strip()
    return Path(override) if override else DEFAULT_FEEDS_FILE


def _load_entries() -> list[tuple[str, list[str], str]]:
    """Parse ``feeds.txt`` into ``(slug, aliases, url)`` tuples in file order.

    Each line is ``slug = url`` with optional parenthesised aliases on the left:
    ``the_drive (peter attia) = <url>`` — so a show can be found by host name too.
    """
    path = _feeds_path()
    if not path.exists():
        return []
    entries: list[tuple[str, list[str], str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        left, _, url = line.partition("=")
        left, url = left.strip(), url.strip()
        alias_match = re.search(r"\(([^)]*)\)", left)
        aliases = (
            [a.strip() for a in alias_match.group(1).split(",") if a.strip()]
            if alias_match
            else []
        )
        slug = re.sub(r"\([^)]*\)", "", left).strip()
        if slug and url:
            entries.append((slug, aliases, url))
    return entries


def load_feeds() -> dict[str, str]:
    """Parse ``feeds.txt`` into an ordered ``{slug: rss_url}`` mapping."""
    return {slug: url for slug, _aliases, url in _load_entries()}


def list_feeds() -> dict[str, str]:
    """Public accessor for the curated feeds (name -> RSS URL)."""
    return load_feeds()


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


# Filler words that carry no matching signal, so "the tim ferriss show" still
# resolves to ``tim_ferriss`` on token overlap.
_STOPWORDS = {"the", "a", "an", "show", "podcast", "with", "and", "of", "experience"}


def _tokens(text: str) -> set[str]:
    return {tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok and tok not in _STOPWORDS}


def resolve_feed(name_or_url: str) -> str:
    """Resolve a feed name to its RSS URL. A raw ``http(s)`` URL passes through.

    Matching is forgiving, in order: exact (normalized) slug, then substring either
    direction, then token overlap ("the tim ferriss show" -> ``tim_ferriss``), then
    fuzzy match for typos ("hubermann" -> ``huberman_lab``). Unknown names raise
    ``ValueError`` listing what is available (surfaces to the loop as an observation,
    not a crash).
    """
    value = (name_or_url or "").strip()
    if not value:
        raise ValueError("No feed name or URL was provided.")
    if value.lower().startswith(("http://", "https://")):
        return value

    entries = _load_entries()
    feeds = {slug: url for slug, _a, url in entries}
    target = _normalize(value)

    # 1. Exact normalized match on a slug or any alias.
    for slug, aliases, url in entries:
        if _normalize(slug) == target or any(_normalize(a) == target for a in aliases):
            return url

    # 2. Substring either direction ("rogan" -> joe_rogan).
    for slug, aliases, url in entries:
        for name in (slug, *aliases):
            norm = _normalize(name)
            if target and (target in norm or norm in target):
                return url

    # 3. Token overlap: score each entry by how many query tokens its slug/aliases share.
    query_tokens = _tokens(value)
    if query_tokens:
        best_url, best_score = None, 0
        for slug, aliases, url in entries:
            name_tokens = _tokens(" ".join((slug, *aliases)))
            score = len(query_tokens & name_tokens)
            if score > best_score:
                best_url, best_score = url, score
        if best_url is not None:
            return best_url

    # 4. Fuzzy match on normalized slugs for typos.
    norm_to_slug = {_normalize(slug): slug for slug in feeds}
    close = difflib.get_close_matches(target, list(norm_to_slug), n=1, cutoff=0.6)
    if close:
        return feeds[norm_to_slug[close[0]]]

    available = ", ".join(feeds) or "(none configured)"
    raise ValueError(
        f"Unknown feed '{name_or_url}'. Pass a raw RSS URL, or one of: {available}."
    )
