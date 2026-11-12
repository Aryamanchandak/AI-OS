# app/api/claude/route.ts — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 23
**Language:** TypeScript (Next.js App Router API route)

---

## What This File Does (Plain English)

This is a thin server-side proxy for the Anthropic Messages API. It exists to keep the Anthropic API key on the server rather than exposing it to the browser. Any POST request to `/api/claude` is forwarded verbatim to `https://api.anthropic.com/v1/messages`, and the Anthropic response (including HTTP status) is forwarded verbatim back to the caller.

---

## How It Actually Works

### Entry Points

Next.js App Router convention: the exported `POST` function is invoked when a `POST` request hits `/api/claude`. No other HTTP methods are handled.

### Data Flow

```
POST /api/claude  (from browser)
  → read ANTHROPIC_API_KEY from process.env
  → if missing: return 500 JSON { error: 'ANTHROPIC_API_KEY not configured' }
  → parse request body as JSON
  → POST to https://api.anthropic.com/v1/messages
      headers: content-type, x-api-key (from env), anthropic-version: '2023-06-01'
      body: request body forwarded verbatim
  → parse Anthropic response as JSON
  → return NextResponse.json(data, { status: anthropicResponse.status })
```

### State Management

None — stateless request handler. Every request is independent.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `POST(request)` | Reads the API key, forwards the request body to Anthropic, and returns the response with the original status code |

### External Dependencies

- `process.env.ANTHROPIC_API_KEY` — must be set in the server environment (`.env.local` for local dev, platform env vars for production)
- `https://api.anthropic.com/v1/messages` — the Anthropic API
- `next/server` — `NextResponse`
- `anthropic-version: '2023-06-01'` — hardcoded API version header

### Error Handling

- Missing `ANTHROPIC_API_KEY`: returns `500` with `{ error: 'ANTHROPIC_API_KEY not configured' }`
- `request.json()` — no try/catch; if the request body is not valid JSON, Next.js throws a 400 (framework behavior), but this code does not explicitly handle it
- Anthropic non-200 responses are forwarded with the original status code — the client receives the Anthropic error JSON directly
- Network errors reaching `api.anthropic.com` propagate as unhandled exceptions — Next.js will return a 500 but with a generic error, not the original message

---

## Non-Technical Decisions Embedded in the Code

- **Verbatim forwarding** — the request body is forwarded to Anthropic without any inspection, validation, or sanitization. The client can send any model, any system prompt, any message list. The proxy adds no restrictions.
- **`anthropic-version: '2023-06-01'`** — the API version is hardcoded, not configured. Upgrading to a new Anthropic API version requires editing this file.
- **Status code passthrough** — `NextResponse.json(data, { status: anthropicResponse.status })` means a `429 Too Many Requests` or `529 Overloaded` from Anthropic is forwarded to the client as-is. The client (`lib/claude.ts`) checks `response.ok` and throws, so this is handled, but the specific status code is available for debugging.
- **No authentication on the proxy itself** — anyone who can reach this endpoint can make Anthropic API calls charged to the configured API key. In a local dev environment (localhost only), this is acceptable. In a deployed environment, this is a significant security gap.
- **No request body size limit** — Next.js has a default body size limit of 4MB, but this route does not configure a custom limit. Sending very large prompts is constrained only by Next.js defaults.
- **No rate limiting** — there is no per-client or global rate limit applied before forwarding to Anthropic. Runaway calls or abuse will directly hit the Anthropic account's rate limits.

---

## Honest Gaps and Risks

- **Open proxy** — any authenticated (or unauthenticated) client can POST arbitrary content to this endpoint and have it billed to the Anthropic API key. In production, this needs authentication (e.g., session token check) or network-level access control.
- **No try/catch on `request.json()`** — a malformed request body (non-JSON Content-Type, truncated body) will throw and surface as an uncaught Next.js error rather than a clean 400 response.
- **No try/catch on the `fetch` to Anthropic** — a network-level failure (DNS, timeout, connection refused) propagates as an unhandled rejection; Next.js will catch it and return a 500 but the response body is a generic Next.js error page, not a JSON error object that `lib/claude.ts` can parse gracefully.
- **`anthropic-version` is never updated automatically** — if Anthropic deprecates `2023-06-01`, requests will start failing silently or with confusing errors.

---

## Developer Notes

This file is the reason `lib/claude.ts` uses a relative URL `/api/claude` instead of calling Anthropic directly. The split exists to prevent the API key from leaking to the client bundle. When running `npm run dev`, this route is served at `http://localhost:3000/api/claude`. To test the proxy independently, you can POST to it with any Anthropic-compatible body. The `ANTHROPIC_API_KEY` environment variable must be set in `.env.local` for local development.
