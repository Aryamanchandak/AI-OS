# app/page.tsx — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 70
**Language:** TypeScript / React (Next.js App Router, Client Component)

---

## What This File Does (Plain English)

This page is a backend smoke test, not a product UI. It renders a single button that fires a hardcoded test request to the `/api/claude` proxy to verify the server layer is working. If the API responds, it displays the text. If it errors, it displays the error. The file itself states: "Phase A: backend layer only. UI coming in Phase B."

---

## How It Actually Works

### Entry Points

Next.js routes this component to `/` (the root URL). It is a `'use client'` component — all logic runs in the browser.

### Data Flow

```
User clicks "Test backend" button
  → setLoading(true), clear error and result
  → POST /api/claude with:
      model: 'claude-sonnet-4-20250514'
      max_tokens: 50
      system: 'You are a concise assistant.'
      messages: [{ role: 'user', content: 'Reply with exactly: "Backend ready."' }]
  → if response not ok: setError(JSON.stringify(data))
  → if ok: extract first text block from data.content[], setResult(text)
  → setLoading(false)
```

### State Management

Three pieces of local React state:
- `result: string` — the Claude text response
- `loading: boolean` — disables the button during the in-flight request
- `error: string` — stringified error JSON or thrown Error message

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `testBackend()` | Fires a hardcoded POST to `/api/claude`, displays the response text or error |
| `Home` (default export) | The page component: renders a button, optional result box, optional error box, and a footer listing the lib files |

### External Dependencies

- `fetch` — browser Fetch API
- `/api/claude` — the server-side Anthropic proxy
- Tailwind CSS — styling classes for layout and color
- `react` — `useState`

### Error Handling

- `try/catch` wraps the entire fetch call; caught errors set `error` to `e.message`
- Non-ok HTTP responses: `data` is JSON-parsed and stringified into the error display (no try/catch on the error path's JSON parse — if the error response is not JSON, this throws again inside the catch block)
- The `finally` block always clears loading

---

## Non-Technical Decisions Embedded in the Code

- The request is **fully hardcoded** — model, tokens, system prompt, user message. This page cannot accept user input; it exists only to prove the proxy works.
- The response text extraction (`data.content?.find(b => b.type === 'text')?.text ?? ''`) is inline here rather than using `lib/claude.ts`. The lib module's `callClaude` does exactly this — the duplication is probably because this page was written as a standalone smoke test without integrating the library.
- The bottom of the page lists all lib files in a static text block: `lib/types.ts · lib/claude.ts · lib/prompts.ts ...`. This is a status checklist comment rendered as visible UI text, not programmatically generated from the actual file list.
- Tailwind classes use dark background (`bg-gray-950`) as the page background — this is the ambient dark theme for the whole app, but it is applied in this component's JSX rather than in `globals.css` or `layout.tsx`.

---

## Honest Gaps and Risks

- **This page is a dead end** — once the real UI is built in Phase B, this page gets replaced entirely. It is not a foundation; it is temporary scaffolding.
- **Error display of non-JSON error responses will throw** — if the API returns a non-JSON response when `res.ok` is false, `JSON.stringify(data)` will fail because the parse on line 25 (`const data = await res.json()`) has already thrown. The outer `catch(e)` would catch it, but the error shown to the user would be the parse error rather than the original API error.
- **The lib files listed in the footer are hardcoded** — if a file is added or removed, this list must be updated manually.
- **No integration with `lib/claude.ts`** — the fetch call in this page duplicates the pattern from `lib/claude.ts` rather than calling it. The lib module exists and is unused by this page.

---

## Developer Notes

This page will be replaced by the full three-pane UI (Phase B). When that happens, the `lib/operations.ts` functions should be the primary interface — not raw `fetch` calls. The `'use client'` directive at the top is required because the component uses `useState`; any API-route-adjacent fetching in the new UI should follow the same pattern of POSTing to `/api/claude` rather than calling Anthropic directly.
