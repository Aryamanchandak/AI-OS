# lib/versioning.ts — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 33
**Language:** TypeScript

---

## What This File Does (Plain English)

This file provides two utilities for the version history feature: one that creates an immutable snapshot of the current document state (for storing in version history), and one that compares two sets of test results to classify each test as a regression, a new pass, or unchanged. It has no I/O of its own — storage is handled by `lib/storage.ts`.

---

## How It Actually Works

### Entry Points

Both exports are consumed by the UI layer (currently `optimizer.jsx`; the TypeScript lib modules are not yet wired to a live UI).

### Data Flow

```
snapshotDocument(document, testResults, conflicts)
  → JSON.parse(JSON.stringify(document))   → deep-cloned document
  → JSON.parse(JSON.stringify(testResults)) → deep-cloned testResults (or null)
  → JSON.parse(JSON.stringify(conflicts))   → deep-cloned conflicts (or null)
  → return { timestamp: Date.now(), document, testResults, conflicts }

classifyTestChanges(prev, current)
  → for each [id, result] in current:
      if no prev result → label 'unchanged'
      if prev passed and current fails → label 'regression'
      if prev failed and current passes → label 'new_pass'
      else → label 'unchanged'
  → return Record<string, 'regression' | 'new_pass' | 'unchanged'>
```

### State Management

None — both functions are pure with no side effects or module-level state. `Date.now()` is the only non-deterministic input.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `snapshotDocument()` | Deep-clones the current document, test results, and conflicts via JSON round-trip; attaches a timestamp; returns an immutable `Version` object |
| `classifyTestChanges()` | Compares previous and current test result maps; labels each test as `'regression'`, `'new_pass'`, or `'unchanged'` |

### External Dependencies

- `lib/types.ts` — imports `Document`, `Version`, `TestResult`, `Conflict`
- No API calls, no I/O

### Error Handling

None — both functions operate on plain data structures. If the input contains non-JSON-serializable values (Date objects, undefined, functions), `JSON.stringify` will silently drop or transform them without throwing.

---

## Non-Technical Decisions Embedded in the Code

- **Deep clone via `JSON.parse(JSON.stringify(...))`** — this is the simplest deep clone approach for plain objects. It is chosen over `structuredClone` (which handles more types) or a library like `lodash.cloneDeep`. The current data model is JSON-compatible, so this is fine, but it is a footgun if anyone adds a `Date`, `Map`, `Set`, `undefined`, or class instance to the data model — those values will be silently lost or transformed.
- **`classifyTestChanges` treats a test with no prior result as `'unchanged'`** rather than `'new'` or `'untracked'`. A test that has never been run before is classified identically to a test that has run and produced the same result. This is a labeling mismatch — the caller cannot distinguish "this test has always passed" from "this test has no prior run data".
- **`testResults` and `conflicts` are conditionally cloned** — if either is `null`, `JSON.parse(JSON.stringify(null))` is still called (via the ternary), which correctly returns `null`. But the ternary is written as `testResults ? JSON.parse(JSON.stringify(testResults)) : null` — safe and readable.

---

## Honest Gaps and Risks

- **`classifyTestChanges` does not handle tests that existed in `prev` but are absent from `current`** — deleted test cases are silently ignored. The function only iterates `current`, so a test that was removed is not flagged as removed.
- **JSON deep-clone will silently corrupt data** if the data model ever includes non-JSON-primitive types. No runtime check warns when this happens.
- **`snapshotDocument` returns a `Version` with `timestamp: Date.now()`** — the timestamp is in milliseconds since epoch. If two snapshots are created in the same millisecond (unlikely but possible under rapid automated edits), they are indistinguishable by timestamp alone. There is no monotonically incrementing version counter.
- **The function is not called by `app/page.tsx`** — the current live page does not use this module. It is consumed only by `optimizer.jsx`, which is currently orphaned from the Next.js routing.

---

## Developer Notes

`classifyTestChanges` is not yet called by any live UI code — `optimizer.jsx` does not call it either. It was written in anticipation of a regression-flagging UI that shows which tests improved or broke across versions. If you add version comparison to the UI, this is the function to wire in. The `'unchanged'` label for new tests with no prior data is the most likely source of confusion when this function is first integrated into the UI — consider adding a fourth classification value `'new'` for that case.
