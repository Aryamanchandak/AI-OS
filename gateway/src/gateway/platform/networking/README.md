# Outbound HTTP client

`__init__.py` defines `OutboundHTTPClient`, the application's reusable `httpx.AsyncClient` wrapper. It configures a default 30-second timeout and disables automatic redirect following. Callers can override the timeout for individual requests.

[Application lifespan](../../app/README.md) constructs one wrapper, passes its client to LLM provider adapters, and exposes it through the dependency container for other outbound calls such as agent-trace retrieval. `close()` asynchronously closes the client on shutdown.

This wrapper does not validate arbitrary user-supplied URLs. Remote chat image fetching uses the separate [SSRF-safe fetcher](../../security/README.md), with its own pinned transport and redirect checks.
