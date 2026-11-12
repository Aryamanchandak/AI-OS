"""Curated feed loading + name resolution."""

import pytest

from podcast_tools.feeds import list_feeds, load_feeds, resolve_feed

EXPECTED_SLUGS = {
    "joe_rogan",
    "founders",
    "dwarkesh",
    "diary_of_a_ceo",
    "rest_is_politics",
}


def test_load_feeds_has_all_curated_shows():
    loaded = load_feeds()
    assert EXPECTED_SLUGS <= set(loaded)
    assert loaded["dwarkesh"] == "https://api.substack.com/feed/podcast/69345.rss"
    assert all(url.startswith("http") for url in loaded.values())
    assert list_feeds() == loaded


def test_resolve_feed_matches_names_loosely():
    joe = load_feeds()["joe_rogan"]
    assert resolve_feed("joe_rogan") == joe
    assert resolve_feed("Joe Rogan") == joe   # spaces + case
    assert resolve_feed("rogan") == joe        # substring


def test_resolve_feed_matches_aliases():
    feeds = load_feeds()
    # Host-name aliases resolve to the show even when the slug is the title.
    assert resolve_feed("peter attia") == feeds["the_drive"]
    assert resolve_feed("sam harris") == feeds["making_sense"]
    assert resolve_feed("dan carlin") == feeds["hardcore_history"]


def test_resolve_feed_fuzzy_and_token_match():
    feeds = load_feeds()
    assert resolve_feed("the tim ferriss show") == feeds["tim_ferriss"]  # token overlap
    assert resolve_feed("hubermann") == feeds["huberman_lab"]            # typo -> fuzzy
    assert resolve_feed("lex") == feeds["lex_fridman"]                   # substring


def test_resolve_feed_passes_raw_urls_through():
    url = "https://example.com/custom/feed.rss"
    assert resolve_feed(url) == url


def test_resolve_feed_unknown_name_raises_with_options():
    with pytest.raises(ValueError) as exc:
        resolve_feed("definitely-not-a-real-show")
    assert "dwarkesh" in str(exc.value)


def test_feeds_file_override(tmp_path, monkeypatch):
    custom = tmp_path / "myfeeds.txt"
    custom.write_text("# comment\nmyshow = https://example.com/x.rss\n", encoding="utf-8")
    monkeypatch.setenv("PODCAST_FEEDS_FILE", str(custom))
    assert load_feeds() == {"myshow": "https://example.com/x.rss"}
    assert resolve_feed("myshow") == "https://example.com/x.rss"
    # Original curated names are no longer present under the override.
    with pytest.raises(ValueError):
        resolve_feed("joe_rogan")
