# lib/claude.ts — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 69
**Language:** TypeScript

---

## What This File Does (Plain English)

This file is the client-side bridge to the Claude API. It provides two exported functions: one that calls Claude and returns a plain string, and one that calls Claude and parses the response as JSON with one automatic retry if parsing fails. All calls are routed through the Next.js API proxy at `/api/claude` rather than hitting Anthropic directly.

---

## How It Actually Works

### Entry Points

`callClaude` and `callClaudeJSON` are the two public exports. They are called from `lib/operations.ts`, which is the only consumer in the TypeScript module tree.

### Data Flow

```
callClaude({ system, userMessage, maxTokens })
  → POST /api/claude  (body: { model, max_tokens, system, messages })
  → await response.json()
  → find first content block where type === 'text'
  → return block.text || ''

callClaudeJSON<T>({ system, userMessage, maxTokens })
  → callClaude(...)
  → strip markdown fences (```json ... ```)
  → JSON.parse(cleaned)
  → if parse fails: retry callClaude with amended system prompt
  → JSON.parse again
  → if still fails: throw with first 500 chars of raw output
```

### State Management

No state. These are pure async functions with no module-level mutable state.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `callClaude()` | Sends a single-turn message to Claude via the `/api/claude` proxy; extracts and returns the text content block |
| `callClaudeJSON<T>()` | Same as `callClaude`, but parses the result as JSON; strips markdown code fences before parsing; retries once with explicit JSON-only instruction if parsing fails |

### External Dependencies

- `fetch` — native browser Fetch API, called against the relative URL `/api/claude`
- Model hardcoded as `claude-sonnet-4-20250514` at the top of the file

### Error Handling

- If the HTTP response is not `ok`, throws: `Claude API error (${status}): ${errText}`
- If JSON parsing fails on first attempt: silently retries with a stronger system prompt instruction
- If JSON parsing fails on second attempt: throws with the first 500 characters of the raw response for debugging
- No timeout is set; if the Anthropic API hangs, this hangs too
- Network errors (DNS failure, connection refused) propagate as unhandled rejections to the caller

---

## Non-Technical Decisions Embedded in the Code

- The model name `claude-sonnet-4-20250514` is hardcoded at the module level as a constant `MODEL`. There is no environment variable or configuration hook — changing the model requires editing this file directly.
- The JSON fence stripping regex (`/^```(?:json)?\s*/i` and `/\s*```$/`) handles only the most common case: a single code block wrapping the entire response. If Claude returns prose followed by a JSON block, this strips nothing and parse fails.
- The retry strategy appends text to the system prompt rather than constructing a fresh conversation. The retry system prompt is `original_system + "\n\nIMPORTANT: Respond with ONLY valid JSON..."` — reasonable for most cases but the appended instruction sits after potentially thousands of characters of the original system prompt.
- `callClaude` uses a relative URL `/api/claude`. This means the function is browser-only by design — calling it from a Node.js server context (e.g., an RSC or server action) will throw because `window.location` is undefined and `fetch('/api/claude')` has no base URL to resolve against.
- `maxTokens` defaults to 2000 for both functions, which each caller can override.

---

## Honest Gaps and Risks

- **Browser-only** — the relative URL `/api/claude` makes `callClaude` and `callClaudeJSON` unusable from server-side Next.js code (API routes, server components). Any future move of logic server-side would require either an absolute URL or a different call pattern.
- **No timeout** — a hung Anthropic request will hang the browser indefinitely, with no user-visible timeout or cancellation.
- **Fence stripping is naive** — if Claude wraps output in triple backticks but also includes explanatory text before the block, the regex leaves the prose in place and `JSON.parse` fails. The retry fires, which may or may not produce clean JSON.
- **No request deduplication or cancellation** — if the user sends two chat messages rapidly, two parallel Claude calls are in-flight with no way to cancel the first.
- **`textBlock?.text || ''`** returns an empty string if Claude returns no text block (e.g., only tool-use blocks). The caller receives `''` rather than an error, which can cause silent failures downstream.

---

## Developer Notes

`lib/operations.ts` is the sole consumer of this file in the TypeScript module tree. `optimizer.jsx` has its own inline duplicates of both functions that call Anthropic directly (no proxy) — those are browser-broken in production and were superseded by this module. If you change the JSON schema retry logic here, verify that `operations.ts`'s callers all handle the error contract. The `callClaudeJSON<T>` generic is typed at the call site in `operations.ts` — mismatches between the declared return type `T` and the actual JSON shape will only surface at runtime.
