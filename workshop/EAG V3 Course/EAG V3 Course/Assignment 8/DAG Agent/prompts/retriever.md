Fetches a daily close-price history for a single ticker.

This skill has `runtime: tool` — it dispatches to `fetch_prices` in
agent/tools.py and never calls the model, so this file documents the contract
rather than instructing a model.

Input:  a node input string containing exactly one ticker symbol.
Output: a JSON object with keys
          ticker, source, points, start_date, end_date, dates, closes

`source` is one of `stooq` (live), `synthetic-fallback` (network failed), or
`degraded-stub` (deliberately degraded, used by the Critic-failure demo).
Downstream nodes and the Critic should treat anything other than `stooq` as
data that must be disclosed in the final answer.
