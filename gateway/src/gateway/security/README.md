# Safe fetching of remote images

`ssrf.py` protects the remote `image_url` fetches performed during LLM request normalization. SSRF means tricking a server into contacting internal or otherwise restricted network addresses. `__init__.py` declares the package.

## How fetching works

1. `prepare_safe_target()` permits HTTP/HTTPS URLs without embedded credentials and resolves the hostname.
2. It rejects targets if any resolved address is private, loopback, link-local, reserved, multicast, or unspecified, including checked IPv4 addresses embedded in IPv6.
3. A custom HTTP transport pins the connection to the validated IP while retaining the logical hostname for the request and TLS handling.
4. `fetch_bytes()` follows redirects manually and repeats validation for each destination. It allows up to four redirects and caps the response at 12 MiB, checking both declared and received size.
5. It returns the bytes and response media type; normalization converts them to a base64 data URL for the provider.

`assert_safe_url()` validates without fetching. Invalid targets, transport failures, oversized downloads, and excessive redirects become HTTP 400 errors. This guard is used by [normalization](../llm/orchestration/README.md); it is not automatically applied to every outbound HTTP call in the application.
