# lib/storage.ts — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 60
**Language:** TypeScript

---

## What This File Does (Plain English)

This file wraps `localStorage` with typed read/write functions for the three persistent data objects: the current document, the project context, and the version history. It is the only file that touches persistent storage. It handles server-side rendering (SSR) safety by checking for `window` before accessing `localStorage`.

---

## How It Actually Works

### Entry Points

Six named exports, called by the UI layer: `saveDocument`, `loadDocument`, `saveContext`, `loadContext`, `saveVersions`, `loadVersions`. The current live page (`app/page.tsx`) does not call any of these — they are currently consumed only by `optimizer.jsx`.

### Data Flow

```
save*(value)
  → if not client (window undefined): return immediately
  → JSON.stringify(value)
  → localStorage.setItem(key, serialized)

load*()
  → if not client: return null or []
  → localStorage.getItem(key)
  → if null: return null or []
  → JSON.parse(raw) cast to typed value
  → if parse throws: return null or []
```

Three localStorage keys are used, defined as constants in `KEYS`:
- `'optimizer:doc'` — the current `Document`
- `'optimizer:context'` — the current `ProjectContext`
- `'optimizer:versions'` — the `Version[]` array

Version saves are capped at 50 entries (`MAX_VERSIONS = 50`). On `saveVersions`, only the last 50 elements of the input array are persisted.

### State Management

This file manages no in-memory state. It is a pure I/O layer over `localStorage`. State ownership lives in the UI (React state in `optimizer.jsx` or the future `app/page.tsx`).

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `isClient()` | Returns `true` if `window` is defined; guards all localStorage access against SSR crashes |
| `saveDocument(doc)` | Serializes a `Document` to `localStorage` under the `'optimizer:doc'` key |
| `loadDocument()` | Reads and deserializes the stored `Document`; returns null on missing or corrupt data |
| `saveContext(ctx)` | Serializes a `ProjectContext` to `localStorage` |
| `loadContext()` | Reads and deserializes the stored `ProjectContext`; returns null on missing or corrupt data |
| `saveVersions(versions)` | Caps the array to the last 50 entries, then serializes and stores the `Version[]` |
| `loadVersions()` | Reads and deserializes the stored `Version[]`; returns `[]` on missing or corrupt data |

### External Dependencies

- `lib/types.ts` — `Document`, `ProjectContext`, `Version`
- `localStorage` — browser global, not available in SSR/Node.js contexts

### Error Handling

- All `load*` functions wrap `JSON.parse` in a try/catch and return `null` or `[]` on any parse error. This means corrupt `localStorage` data is silently discarded — the user loses their work with no warning or recovery path.
- SSR safety: `isClient()` returns `false` in a Node.js environment; all functions return early with null/empty rather than throwing a ReferenceError on `window`.
- `save*` functions do not catch `localStorage.setItem` errors. If `localStorage` is full (storage quota exceeded), `setItem` throws a `QuotaExceededError` which propagates unhandled to the caller.

---

## Non-Technical Decisions Embedded in the Code

- **50-version cap** (`MAX_VERSIONS = 50`) — versions are capped on save by slicing to the last 50. Older versions are silently dropped when new ones are added beyond the cap. There is no warning or UI indication that a version was dropped.
- **No migration or schema validation** — the `loadDocument` function casts `JSON.parse(raw)` directly to `Document` without checking whether the stored shape actually matches the current `Document` type. If the `Document` type changes between code versions, old stored data will be loaded as a `Document` with missing or extra fields, causing runtime errors when the code accesses expected fields.
- **No cross-tab synchronization** — `localStorage` changes from another browser tab do not trigger any event or update in the running app. If the user opens two tabs, each tab independently reads and writes, and the last write wins.
- **The version cap (`slice(-50)`) happens on save, not on load** — if `loadVersions` returns more than 50 entries (e.g., from a previous version of the code with a higher cap), all entries are returned to the caller. The cap is only enforced on writes.

---

## Honest Gaps and Risks

- **Silent data loss on corrupt `localStorage`** — any `JSON.parse` error in a load function returns null/empty with no error signal. The user sees an empty state as if they never used the app before, with no recovery path and no explanation.
- **No schema migration** — loading data serialized by an older version of the code will silently produce a mismatched object. TypeScript's type assertions (`as Document`) only satisfy the compiler; they do not validate at runtime.
- **`saveVersions` drops old entries silently** — the 50-version cap is enforced by slicing, but the UI currently has no indicator that history was pruned. A user who expects to roll back 60 versions will be surprised.
- **QuotaExceededError propagates unhandled** — for a long session with many large versions, `localStorage` could fill up. The app would crash on the next save with an unhandled exception.
- **Not used by the live application** — `app/page.tsx` does not call any of these functions. Storage is currently dead code from the perspective of the running Next.js app. Only `optimizer.jsx` would call it, but `optimizer.jsx` is not routed.

---

## Developer Notes

This module is ready to use — it only needs to be wired into the UI state management. The recommended pattern is to call `saveDocument(doc)` after every section edit and `loadDocument()` on app mount (after hydration). Because all functions are SSR-safe, they can be called from client components without additional guards. The `isClient()` guard is internal — callers do not need to check it.
