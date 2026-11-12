# `fetch`  ·  group: `utility`

1 registered MCP tool(s). Everything for this tool lives in this folder.

### `fetch_url(url: 'str', timeout: 'int' = 30) -> 'dict'`

Fetch clean markdown from an HTTP or HTTPS URL via crawl4ai headless Chromium.
Example: `fetch_url("https://example.com")`.

The tool fetches one explicit URL; it does not search for or rank relevant
documents. Use `web_search` first when discovery is needed, then pass the chosen
URL to this tool.

Validation before browser launch:

- rejects blank URLs;
- allows only `http://` and `https://`;
- requires a hostname;
- rejects embedded credentials;
- rejects malformed ports;
- rejects localhost and literal private/local/reserved/multicast IP URLs.

The crawl is capped at 30 seconds. A lower `timeout` may be passed by the
caller, but higher values are capped to 30 seconds.

Returns a dictionary with:

- `status`
- `content_type`
- `length_bytes`
- `text`

Cybersecurity caveat: this tool reduces obvious risky inputs and prevents
indefinite hangs, but it is still a headless browser visiting arbitrary web
content. It does not yet enforce a domain allowlist, perform DNS-based private
network blocking, scan fetched content, or guarantee safety against all browser
or site-level attacks.

**Files:** `tool.py`, `__init__.py` (registration).
