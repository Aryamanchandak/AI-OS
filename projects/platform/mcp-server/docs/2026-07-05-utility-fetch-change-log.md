# 2026-07-05 Utility Fetch Change Log

This note records the approved one-tool change for `tools/utility/fetch/`.

## Decision

- Keep `fetch_url` as one MCP tool in its own folder.
- Keep crawl4ai headless Chromium as the fetch/extraction implementation.
- Treat `fetch_url` as a single-URL fetcher, not a search or relevance-ranking
  tool.
- Add URL validation before browser launch.
- Enforce a hard 30-second maximum timeout.

## Code Changes

### `tools/utility/fetch/tool.py`

- Added validation for blank URLs, scheme, hostname, embedded credentials, and
  malformed ports.
- Limited supported schemes to `http://` and `https://`.
- Rejected localhost and literal private/local/reserved/multicast IP URLs.
- Changed the default timeout to 30 seconds.
- Capped caller-provided timeout values to 30 seconds.
- Wrapped crawl4ai execution in `asyncio.wait_for(...)`.
- Raised a clear timeout error when the crawl exceeds the enforced timeout.

## Documentation

### `tools/utility/fetch/README.md`

- Documented that `fetch_url` fetches one explicit URL and does not perform
  discovery or relevance ranking.
- Documented validation rules, timeout behavior, return shape, and cybersecurity
  caveats.

## Caveats

- The tool does not enforce a domain allowlist yet.
- The tool does not perform DNS resolution to block hostnames that resolve to
  private network addresses.
- The tool does not inspect redirect chains before crawl4ai/browser navigation.
- The tool does not scan fetched content for malware or phishing risk.
