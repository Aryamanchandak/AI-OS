# `providers/fetch/__init__.py`

This module is the pipeline's only way to pull the actual content of a web page. It does two jobs: (1) validate that a URL is safe to fetch at all — rejecting local/private/loopback destinations to close off SSRF — and (2) perform the HTTP GET with manual redirect-following, size capping, retry, and HTML-to-plain-text extraction. It is a hand-rolled security boundary as much as an HTTP client.

## Main entry points

### `normalize_url(value: str) -> str`
Canonicalizes a URL string for two purposes: dedup keying (so the same article reached via different query strings/casing collapses to one key) and as a first-pass safety filter. It:
- Lowercases scheme and host, IDNA-encodes the host.
- Rejects anything that isn't `http`/`https` with a hostname (`UnsafeUrl`).
- Rejects `localhost`, `localhost.localdomain`, and any `*.local` host by name, and rejects any literal IP address that isn't globally routable (via `ipaddress.is_global`) — this catches `127.0.0.1`, `10.x`, `192.168.x`, link-local, etc., but only when the URL itself contains a literal IP.
- Strips tracking query params: a hardcoded set `{gclid, fbclid, mc_cid, mc_eid, ref, source}` plus anything starting with `utm_`.
- Collapses duplicate slashes in the path and strips a trailing slash.
- Drops the fragment entirely.

Malformed input (bad authority, bad IDNA label) is caught and re-raised as `UnsafeUrl` rather than leaking a raw `ValueError`/`UnicodeError` — the inline comment explains this is so `normalize_batch` (in `ingest/__init__.py`) doesn't die on one bad URL in a batch.

**Important gap:** `normalize_url` only catches SSRF via literal IP addresses or `localhost`/`.local` names in the URL string. A hostname like `internal.corp.example` that *resolves* to a private IP passes straight through — DNS is never consulted here. That's what the next function is for.

### `assert_public_url(value, resolver=socket.getaddrinfo) -> str`
Calls `normalize_url` first, then actually resolves the hostname (via `socket.getaddrinfo` by default, injectable for tests) and rejects the URL if *any* resolved address is non-global (`UnsafeUrl`). This is the real SSRF guard — it closes the DNS-rebinding-style gap left by `normalize_url` alone. Note it re-checks `localhost`/`.local` redundantly (already covered by `normalize_url`), and lets `OSError` from resolution failure surface as `UnsafeUrl` too (so "no such host" and "resolves to a private IP" both come back the same exception type, with different messages).

This function is called once per redirect hop inside `PageFetcher.fetch` — i.e., every hop is independently re-validated, so a redirect chain can't be used to smuggle the fetcher onto an internal address after the first hop passed.

### `class UnsafeUrl(ValueError)`
The single exception type used for every URL-safety rejection (malformed URL, non-HTTP scheme, local/private destination, DNS resolution failure). Callers that want to distinguish "URL was unsafe" from other fetch failures can catch this specifically; `ingest/__init__.py` does exactly that (imports `UnsafeUrl` but currently catches it via the broader `except Exception` in `pre_read`).

### `class FetchResult` (frozen dataclass)
The return value of a successful fetch: `url` (original, normalized), `final_url` (post-redirect, normalized), `title` (extracted from `<title>`, best-effort), `text` (extracted body, truncated), `content_type`, `retrieved_at` (UTC timestamp).

### `class PageFetcher`
Constructed with a `Settings` object and an optional `httpx.BaseTransport` (the transport hook exists purely so tests can inject a fake transport — not exercised in the current test file, which only tests `normalize_url`/`assert_public_url`).

`fetch(url: str) -> FetchResult` does the real work:
1. Validates the URL with `assert_public_url`.
2. Opens an `httpx.Client` with `timeout=settings.fetch_timeout_seconds`, `follow_redirects=False` (redirects are followed manually, not by httpx), and the injected transport.
3. Loops up to `settings.fetch_redirect_limit + 1` times (each iteration is one hop). Inside each hop, retries up to `settings.fetch_retry_limit + 1` times on `httpx.TimeoutException`/`httpx.TransportError`.
4. Sends `GET` with headers `User-Agent: ConsequenceRadar/0.1 (+research)` and `Accept: text/html,text/plain;q=0.9` (both hardcoded, not configurable).
5. If the response is a redirect (`response.is_redirect`), resolves the `Location` header against the current URL, re-validates it with `assert_public_url`, and continues the outer loop to the next hop.
6. Otherwise: calls `response.raise_for_status()` (raises `httpx.HTTPStatusError` on 4xx/5xx — uncaught here, propagates to the caller), checks the `Content-Type` header against a hardcoded allow-list `{"text/html", "text/plain", "application/xhtml+xml"}` and raises plain `ValueError` if it's not in the list or missing.
7. Checks `Content-Length` against `settings.fetch_max_bytes`; if the header is missing or unparseable it's treated as `0` (not a rejection) — the actual enforcement is the streaming byte counter in the next step, so a lying/absent `Content-Length` doesn't bypass the cap.
8. Streams the body via `response.iter_bytes()`, accumulating chunks and raising `ValueError` the moment total bytes exceed `fetch_max_bytes` — this aborts mid-stream rather than downloading the whole oversized body first.
9. Decodes with `response.encoding or "utf-8"`, `errors="replace"` (never raises on bad encoding, silently substitutes replacement characters).
10. Extracts body text: if `content_type == "text/plain"`, the raw decoded text is used as-is; otherwise `trafilatura.extract(...)` runs with `include_comments=False, include_tables=False, favor_precision=True`. If trafilatura returns `None` (couldn't extract meaningful content), the result is silently `""` — no error, no signal to the caller other than an empty `text` field.
11. Extracts the `<title>` via a regex (`<title[^>]*>(.*?)</title>`, case-insensitive, dot-matches-newline) over the raw HTML, not through trafilatura or any HTML parser. Whitespace is collapsed. If no match, title is `""`.
12. Returns `FetchResult` with `text` truncated to the first **80,000 characters** (hardcoded, not from `Settings`) — this happens regardless of what `max_chars` a caller like `ingest.pre_read` (default 8000) will further truncate to; the 80k cap is fetch's own ceiling, independent of downstream truncation.

### Retry/redirect control flow — non-obvious bits
- Retries are scoped to *transport-level* failures only (timeout, connection error). HTTP error status codes (`raise_for_status()`), bad content-type, and oversized-response `ValueError`s are **not** retried — they raise immediately and propagate out of `fetch()`.
- The `for...else` on the inner retry loop: if the loop exhausts all attempts without hitting `break` (i.e., every attempt raised and was caught, but the last one didn't re-raise because... actually on the final attempt `attempt >= fetch_retry_limit` is true so it always re-raises) — practically, `last_error` is re-raised via `raise last_error` inside the `else` only reachable if the loop somehow completes without exception, which given the logic won't normally happen; this is defensive/redundant code, not a distinct behavior path.
- If the redirect loop runs `fetch_redirect_limit + 1` times without terminating in a non-redirect response, the function falls through to `raise ValueError("redirect limit exceeded")` at the very end.
- All of `httpx.HTTPStatusError`, `ValueError` (bad content-type, oversized response, redirect limit), and `UnsafeUrl` are allowed to propagate uncaught out of `PageFetcher.fetch`. The module does no logging and swallows nothing except non-fatal edge cases (bad `Content-Length` header, bad body encoding, missing/unextractable title or body text).

## Hardcoded values worth flagging
- User-Agent string and Accept header (not configurable).
- Content-type allow-list (`text/html`, `text/plain`, `application/xhtml+xml`) — anything else, including `application/json` or `application/pdf`, is rejected outright.
- 80,000-character truncation ceiling on returned text, independent of `Settings`.
- trafilatura extraction flags (`include_comments=False, include_tables=False, favor_precision=True`) are fixed, not configurable per call.
- Tracking-parameter strip list in `normalize_url` (`gclid, fbclid, mc_cid, mc_eid, ref, source`, plus `utm_*` prefix) is a fixed set, not sourced from `Settings`.

Configurable knobs (all via `Settings`, read at `PageFetcher` construction/call time): `fetch_timeout_seconds` (default 12.0s), `fetch_max_bytes` (default 1.5MB), `fetch_redirect_limit` (default 4), `fetch_retry_limit` (default 1) — see `src/consequence_radar/config/__init__.py`.

## Connects to
Grounded by `grep -rl` over `src/`:
- `src/consequence_radar/ingest/__init__.py` — imports `PageFetcher, UnsafeUrl, normalize_url`. `normalize_url` is used in `normalize_batch` to dedupe/canonicalize incoming `NewsItem` URLs before they enter the pipeline. `pre_read` calls `fetcher.fetch(canonical)` per news item (skipping the fetch entirely when the item already supplies a long-enough headline+snippet), wrapping the call in a bare `except Exception` that stores `str(exc)` as `failure_reason` on a `DiscoveryExtract` rather than propagating — so at the ingest boundary, every failure mode from this module (`UnsafeUrl`, `httpx.*`, `ValueError`) becomes an equivalent "fetch failed, use supplied text only" outcome, and the specific exception type is discarded except for its message string.
- `src/consequence_radar/research/__init__.py` — imports `PageFetcher, normalize_url`. `retrieve_for_tasks` calls `fetcher.fetch(canonical)` per search hit to pull full source text for evidence gathering; this call site is *not* wrapped in a broad except in the excerpt seen, so a raised exception here (e.g., a 404, oversized page, or blocked content-type) would propagate up and likely abort the research cycle — worth confirming against the full function if error resilience there matters.
- `src/consequence_radar/pipeline/__init__.py` — imports `PageFetcher` and constructs the default instance (`self.fetcher = fetcher or PageFetcher(settings)`) that's threaded through `pre_read` and `retrieve_for_tasks`. This is the top-level wiring point; `PageFetcher` itself holds no state beyond `settings`/`transport`, so one instance is reused across a whole pipeline run.

Depends on: `consequence_radar.config.Settings` (the four `fetch_*` fields) and the third-party libraries `httpx` (HTTP client) and `trafilatura` (HTML content extraction).
