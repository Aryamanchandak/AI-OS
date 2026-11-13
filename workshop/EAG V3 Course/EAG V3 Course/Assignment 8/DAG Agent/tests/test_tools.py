"""Ticker parsing — regression test for the 'Fetch' bug.

The Planner writes node inputs as sentences, so a case-insensitive scan
matches the first short English word instead of the ticker, and every branch
of the fan-out silently fetches the same wrong series.
"""

import json

import pytest

from agent import tools


class TestParseTicker:
    @pytest.mark.parametrize("spec,expected", [
        ("NVDA", "NVDA"),
        ("Fetch one year of daily closes for NVDA.", "NVDA"),
        ("Fetch one year of daily closes for AMD, ending today", "AMD"),
        ("Get the price history for INTC over the last year", "INTC"),
        ("Retrieve F (Ford) daily closes", "F"),
    ])
    def test_extracts_the_uppercase_ticker(self, spec, expected):
        assert tools._parse_ticker(spec) == expected

    def test_does_not_match_capitalised_english_words(self):
        # "Fetch" is Capitalised, not ALL-CAPS.
        assert tools._parse_ticker("Fetch closes for TSLA") == "TSLA"

    def test_raises_when_there_is_no_ticker(self):
        with pytest.raises(ValueError, match="could not find a ticker"):
            tools._parse_ticker("fetch some prices please")


class TestFetchPrices:
    def test_returns_a_well_formed_payload(self):
        payload = json.loads(tools.fetch_prices("Fetch closes for NVDA"))
        assert payload["ticker"] == "NVDA"
        assert payload["points"] == len(payload["closes"])
        assert all(c > 0 for c in payload["closes"])
        assert payload["source"]
        assert payload["start_date"] and payload["end_date"]
        # The full date vector is intentionally not shipped downstream.
        assert "dates" not in payload

    def test_distinct_tickers_give_distinct_series(self):
        a = json.loads(tools.fetch_prices("Fetch closes for NVDA"))
        b = json.loads(tools.fetch_prices("Fetch closes for AMD"))
        assert a["ticker"] != b["ticker"]
        assert a["closes"] != b["closes"]

    def test_degraded_ticker_returns_a_short_labelled_series(self):
        tools.DEGRADED_TICKERS.add("AMD")
        try:
            payload = json.loads(tools.fetch_prices("Fetch closes for AMD"))  # first fetch
            assert payload["source"] == "degraded-stub"
            assert payload["points"] < 200
        finally:
            tools.DEGRADED_TICKERS.discard("AMD")

    def test_synthetic_series_is_deterministic(self):
        a, _, _ = tools._synthetic("NVDA", 50)
        b, _, _ = tools._synthetic("NVDA", 50)
        assert a == b

    def test_degradation_is_one_shot_so_recovery_can_succeed(self):
        tools.DEGRADED_TICKERS.add("AMD")
        try:
            first = json.loads(tools.fetch_prices("Fetch closes for AMD"))
            second = json.loads(tools.fetch_prices("Fetch closes for AMD"))
            assert first["source"] == "degraded-stub"
            assert second["source"] != "degraded-stub"
            assert second["points"] >= 200
        finally:
            tools.DEGRADED_TICKERS.discard("AMD")
