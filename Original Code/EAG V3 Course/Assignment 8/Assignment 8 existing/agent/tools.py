"""Tools available to `runtime: tool` skills.

fetch_prices tries Stooq's keyless CSV endpoint first, then falls back to a
deterministic synthetic series.

NOTE ON LIVE DATA: as of this build, stooq.com serves a JavaScript browser
challenge to non-browser clients, so the CSV endpoint returns HTML and the
fallback is what actually runs here. The `source` field always says which
path produced the numbers, the Formatter is required to disclose a non-live
source, and the Critic can see it — so a synthetic series is never silently
presented as market data. For genuinely live prices, swap _from_stooq for a
keyed provider; nothing else in the agent changes.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import math
import urllib.error
import urllib.request

STOOQ = "https://stooq.com/q/d/l/?s={sym}.us&i=d"

# Deliberately breakable: used by the Critic-fail demo run.
# One-shot by default — the first fetch of a degraded ticker returns a short
# series, later fetches are healthy. That models a transient upstream and lets
# the recovery splice actually produce a corrected answer. Set STICKY_DEGRADE
# to keep failing, to exercise the recovery-budget path instead.
DEGRADED_TICKERS: set[str] = set()
STICKY_DEGRADE = False


def fetch_prices(spec: str, days: int = 252) -> str:
    """`spec` is a ticker symbol, optionally with surrounding prose."""
    ticker = _parse_ticker(spec)

    if ticker in DEGRADED_TICKERS:
        # Simulates a partial upstream: only a handful of points come back.
        if not STICKY_DEGRADE:
            DEGRADED_TICKERS.discard(ticker)   # one-shot: the refetch succeeds
        closes, dates, _ = _synthetic(ticker, 5)
        source = "degraded-stub"
    else:
        try:
            closes, dates = _from_stooq(ticker, days)
            source = "stooq"
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            closes, dates, source = _synthetic(ticker, days)
            source = f"synthetic-fallback ({type(exc).__name__})"

    return json.dumps(
        {
            "ticker": ticker,
            "source": source,
            "points": len(closes),
            "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else None,
            # The full date vector is deliberately omitted: downstream nodes
            # only need the ordered closes, and shipping 252 date strings into
            # every node's context wastes a large share of the prompt budget.
            "closes": closes,
        },
        indent=2,
    )


def _parse_ticker(spec: str) -> str:
    """A ticker is an ALL-CAPS 1-5 letter token.

    Case matters: the node input is a sentence ("Fetch one year of daily
    closes for NVDA"), so lowercasing first would match 'Fetch'.
    """
    candidates = [
        t.strip(".,:;'\"()")
        for t in spec.replace(",", " ").split()
    ]
    for token in candidates:
        if 1 <= len(token) <= 5 and token.isalpha() and token.isupper():
            return token
    raise ValueError(f"could not find a ticker (ALL-CAPS, 1-5 letters) in {spec!r}")


def _from_stooq(ticker: str, days: int) -> tuple[list[float], list[str]]:
    url = STOOQ.format(sym=ticker.lower())
    with urllib.request.urlopen(url, timeout=15) as resp:
        body = resp.read().decode()

    rows = list(csv.DictReader(io.StringIO(body)))
    if not rows or "Close" not in (rows[0] if rows else {}):
        raise ValueError(f"stooq returned no usable rows for {ticker}")

    rows = rows[-days:]
    dates = [r["Date"] for r in rows]
    closes = [float(r["Close"]) for r in rows]
    if len(closes) < 30:
        raise ValueError(f"stooq returned only {len(closes)} rows for {ticker}")
    return closes, dates


def _synthetic(ticker: str, days: int) -> tuple[list[float], list[str], str]:
    """Deterministic pseudo-random walk seeded from the ticker."""
    seed = int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)
    price = 50.0 + (seed % 200)
    drift = ((seed >> 8) % 40 - 12) / 10000.0
    vol = 0.008 + ((seed >> 16) % 20) / 1000.0

    closes, dates = [], []
    today = dt.date.today()
    state = seed
    for i in range(days):
        state = (1103515245 * state + 12345) % (2**31)
        shock = (state / 2**31 - 0.5) * 2 * vol
        price *= math.exp(drift + shock)
        closes.append(round(price, 2))
        dates.append(str(today - dt.timedelta(days=days - i)))
    return closes, dates, "synthetic"


REGISTRY = {"fetch_prices": fetch_prices}
