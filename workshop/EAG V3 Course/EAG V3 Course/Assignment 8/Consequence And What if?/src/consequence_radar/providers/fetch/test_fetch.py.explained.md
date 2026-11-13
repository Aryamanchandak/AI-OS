# `providers/fetch/test_fetch.py`

Unit tests for the URL-safety layer of `providers/fetch/__init__.py` — `normalize_url` and `assert_public_url`. Nothing in this file exercises `PageFetcher.fetch` itself (no HTTP call, real or mocked); the actual network-facing method has no test coverage here.

## What's tested

One test function, `test_url_normalisation_and_safety`, with four assertions:

1. **Normalization**: `normalize_url("HTTPS://Example.COM/a?utm_source=x&b=2#frag")` must equal `"https://example.com/a?b=2"` — verifies scheme/host lowercasing, `utm_*` stripping, and fragment removal in one shot.
2. **Happy path for DNS-backed safety check**: `assert_public_url("https://example.com", resolver=public_resolver)` must return a string starting with `"https://"` — a smoke test that a normal public host passes through.
3. **Name-based rejection**: `assert_public_url("http://localhost/a", resolver=public_resolver)` must raise `UnsafeUrl` — confirms the hostname blocklist works even when the injected resolver would have returned a public address (i.e., the `localhost`/`.local` name check happens before or independent of DNS resolution).
4. **DNS-based rejection**: `assert_public_url("http://example.com", resolver=private_resolver)` must raise `UnsafeUrl` — this is the important one: a hostname that looks innocuous but resolves (per the injected resolver) to `127.0.0.1` must still be rejected. This is the test that proves the DNS-rebinding-style SSRF gap is actually closed, not just asserted in a comment.
5. **Scheme rejection**: `normalize_url("file:///etc/passwd")` must raise `UnsafeUrl` — non-HTTP(S) schemes are rejected at the normalization stage, before any resolution is attempted.

## Mocking strategy

No HTTP mocking library and no real network access are used. Instead, `PageFetcher`'s design already takes `resolver` as an injectable parameter on `assert_public_url` (default `socket.getaddrinfo`), so the tests substitute two trivial fake resolvers:
- `public_resolver`: always returns `93.184.216.34` (a real public IP — the old example.com address) regardless of the hostname passed in.
- `private_resolver`: always returns `127.0.0.1` regardless of the hostname passed in.

This means the tests are checking the *is_global* branching logic and the local-name blocklist, not real DNS behavior, and not the HTTP client at all. `httpx`, `trafilatura`, `Settings`, and `PageFetcher` itself are never touched in this file — `PageFetcher` isn't imported or instantiated. Consequently, none of the retry logic, redirect handling, byte-cap streaming, content-type allow-list, or text extraction described in `fetch/__init__.py.explained.md` has any automated test coverage as of this file.

## Why this matters

`assert_public_url` is the module's actual SSRF defense (`normalize_url` alone doesn't catch a hostname resolving to a private address). These four assertions are a minimal but targeted regression guard for that specific security property — if someone weakens the `is_global` check or the local-hostname blocklist, this test fails immediately. It does not, however, guard against regressions in the fetch mechanics themselves (timeouts, retries, size limits, content-type filtering) — those remain unverified by any test in this directory.
