# optimizer.jsx — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 1212
**Language:** JavaScript / React (not TypeScript, no framework routing)

---

## What This File Does (Plain English)

This is the original monolith — the prototype from which the `lib/` modules were extracted. It contains the complete application in one file: Claude API helpers, all five system prompts, core operation functions, a diff algorithm, a snapshotting function, and a working scaffolding UI. It also contains a 280-line comment block detailing the intended production UI design. The file is not routed through Next.js — it is a reference artifact and prototype, not a live page.

---

## How It Actually Works

### Entry Points

The default export is a React component called `App`. It is not referenced by any Next.js route — it would need to be imported and rendered from a page file to be live. The file can be run standalone in any React environment that supports JSX.

### Data Flow

The file is structured in numbered sections (1–7):

**1. Claude API Helpers** (`callClaude`, `callClaudeJSON`) — call Anthropic directly from the browser at `https://api.anthropic.com/v1/messages`. This requires the API key to be in the browser, which is a security problem. In the refactored Next.js project, this role is taken over by `lib/claude.ts` + `app/api/claude/route.ts`.

**2. Prompts** — five constant/function prompts identical to `lib/prompts.ts`. These are inline duplicates.

**3. Core Operations** (`detectSections`, `extractContext`, `iterateSection`, `detectConflicts`) — identical in behavior to `lib/operations.ts`, with one exception: these call the inline `callClaudeJSON` (which hits Anthropic directly) rather than going through the proxy.

**4. Test Runner** (`renderTemplate`, `evaluateAssertion`, `runTest`) — the assertion engine, also duplicated in `lib/operations.ts`. The Jaccard similarity in this file computes over Sets (deduplicating tokens) while the TypeScript version computes over an array (allowing duplicates) — the two produce different similarity scores.

**5. Diff** (`diffLines`) — identical to `lib/diff.ts`.

**6. Versioning** (`snapshotDocument`) — creates deep-cloned version snapshots. Note: `classifyTestChanges` is not present here; it exists only in `lib/versioning.ts`.

**7. Scaffolding UI** (`App` component) — a working three-pane React UI (section list, chat, diff/tests/conflicts) built with inline style objects.

### State Management (App component)

All state is in the `App` component's `useState` calls:

| State variable | Type | Purpose |
|---|---|---|
| `mode` | `'prompt' \| 'plan'` | Which operating mode is active |
| `rawInput` | `string` | The user's pasted document text |
| `contextRaw` | `string` | The user's freeform project context text |
| `projectContext` | `object \| null` | The extracted structured context |
| `document` | `object \| null` | The current document with sections and testCases |
| `selectedSectionId` | `string \| null` | Which section is active in the middle pane |
| `chatBySection` | `Record<string, Message[]>` | Per-section chat history |
| `chatInput` | `string` | Current chat textarea value |
| `conflicts` | `Conflict[]` | Current conflict list (plan mode) |
| `testResults` | `Record<string, TestResult>` | Most recent test results (prompt mode) |
| `versions` | `Version[]` | Version history array |
| `busy` | `string` | Label for in-progress operation; empty string when idle |
| `error` | `string` | Current error message |
| `previousSection` | `object \| null` | The section state before the last edit (for diff) |

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `callClaude()` | Browser→Anthropic direct call (no proxy); requires API key in browser |
| `callClaudeJSON()` | Parses Claude's response as JSON with one retry; fence-stripping |
| `detectSections()` | Calls Claude to split input into sections; assigns `s1..sN` IDs |
| `extractContext()` | Calls Claude to parse a project context dump |
| `iterateSection()` | Calls Claude for one chat turn on a section; returns rewritten content + reasoning |
| `detectConflicts()` | Calls Claude to find cross-section contradictions/redundancies/orphans |
| `renderTemplate()` | Substitutes `{{var}}` tokens; leaves unresolved tokens unchanged |
| `evaluateAssertion()` | Routes one assertion type to substring/structural/semantic/reference evaluator |
| `runTest()` | Composes prompt from sections, calls Claude, evaluates all assertions |
| `diffLines()` | LCS-based line diff; returns `{type, text}[]` |
| `snapshotDocument()` | Deep-clones document + testResults + conflicts into a Version object |
| `wrap()` | Utility: sets `busy` label, clears error, runs async fn, clears busy on completion |
| `handleAnalyzeInput()` | Calls `detectSections`, resets document state |
| `handleExtractContext()` | Calls `extractContext`, sets projectContext |
| `handleSendMessage()` | Calls `iterateSection`, updates section content and chat history |
| `handleAcceptContextUpdate()` | Appends a suggested update to contextRaw and re-extracts |
| `handleRunTests()` | Runs all test cases sequentially, updates testResults |
| `handleAddSampleTest()` | Adds a hardcoded sample test case with two assertions |
| `handleRollback()` | Replaces current document/results/conflicts with a version snapshot |
| `handleExport()` | Joins all section contents and writes to clipboard |

### External Dependencies

- `React` — imported with namespace import (`import React, ...`); not using JSX transform auto-import
- `https://api.anthropic.com/v1/messages` — called directly from the browser (broken in production without the API key on the client)
- `navigator.clipboard.writeText` — for export; not guarded, may fail on HTTP (non-HTTPS) origins
- `Date.now()`, `new Date().toLocaleTimeString()` — for timestamps and version labels

### Error Handling

- `wrap()` catches any thrown error, sets it to the `error` state string, and logs it to console. This is the universal error boundary for all handler functions.
- `runTest` catches Claude API errors and returns a failed TestResult rather than throwing.
- `evaluateAssertion` structural branch catches JSON parse errors.
- No error handling for `handleAcceptContextUpdate` — it calls `extractContext` inside `wrap` via a callback, but the outer `wrap` call on `handleExtractContext` is not reused — instead a new inline `wrap` is called. This is correct but potentially confusing.

---

## Non-Technical Decisions Embedded in the Code

- **The 280-line comment block (lines 1–295)** is a detailed UI spec written as structured prose. It describes the intended production three-pane UI, chat message rendering, test case editor UI, diff view details, version history UX, export options, keyboard shortcuts, and explicit constraints ("no streaming", "no mobile V1", "no multi-user"). This document-in-a-comment pattern is unusual — it was written to be handed to an AI coding assistant.
- **`document` is used as a React state variable name** — this shadows the global `document` (the browser DOM). Inside the `App` component, `document` refers to the application document state, not `window.document`. This could cause confusion in any code that tries to use browser DOM APIs inside the component.
- **The `handleSendMessage` function has a stale closure bug** — on line 896 (in the version snapshot call), `snapshotDocument(updatedDoc, testResults, conflicts)` uses the closure `conflicts` rather than the freshly computed `newConflicts` from the conflict detection call a few lines earlier. In plan mode, after an edit that produces a conflict, the first version snapshot stores the *old* conflict state, not the newly detected conflicts. The next edit will correctly store the previous edit's conflicts. This is a real bug that affects version history accuracy in plan mode.
- **Rollback via click on version list** — `handleRollback` is triggered by clicking a version row, with no confirmation step. Clicking a version immediately replaces all current state. There is no "preview then confirm" flow.
- **`handleAddSampleTest` adds a hardcoded test** — the "test" that gets added has `assertions: [substring must_include 'example', semantic 'Output is helpful and direct']`. The substring target `'example'` is almost certainly wrong for real prompts; it's a placeholder the user must edit in code (there is no test editor UI in this scaffold).
- **The scaffolding UI uses inline style objects (`ui.*`)** rather than Tailwind — opposite convention from `app/page.tsx` and the rest of the Next.js project.
- **Mode toggle does not reset document** — the user can switch between Prompt and Plan mode while a document is loaded. Switching mode while viewing a document that was analyzed as a prompt changes the `mode` state, which affects what the conflict detector and other prompts receive, but does not re-analyze the document with the new mode's section vocabulary.

---

## Honest Gaps and Risks

- **Direct Anthropic call** — `callClaude` in this file calls `https://api.anthropic.com/v1/messages` directly. In a browser, this requires `CORS` to be allowed by Anthropic (it is not) and requires the API key to be sent from the browser (exposing it in browser dev tools). This call will fail in a standard browser environment.
- **Stale conflict snapshot bug** — `snapshotDocument(updatedDoc, testResults, conflicts)` in `handleSendMessage` uses the pre-edit `conflicts` value, not `newConflicts`. Version history in plan mode records stale conflict data for the first iteration after an edit.
- **`document` state variable name shadows DOM global** — potential confusion; rename to `promptDoc` or `activeDoc` when refactoring.
- **No persistence** — this component never calls `lib/storage.ts`. All state is lost on page reload.
- **`handleAcceptContextUpdate` re-extracts immediately** but uses `contextRaw + '\n' + update` while `contextRaw` still holds the pre-update value (the `setContextRaw` has been called but React batches state updates). The `extractContext` call may receive the correct concatenated string (because it's built from the old value inline), but the textarea won't reflect the update until after the re-render. This is subtle but functionally correct for the API call, misleading visually until re-render.
- **`navigator.clipboard` may be undefined** — `handleExport` uses optional chaining (`navigator.clipboard?.writeText`), so if clipboard is unavailable (non-HTTPS, denied permission), the export silently does nothing.
- **No TypeScript** — this file is `.jsx`, not `.tsx`. The type safety provided by `lib/types.ts` does not apply here.

---

## Developer Notes

This file is the prototype that preceded the `lib/` module split. The intended workflow is: iterate on logic in this file during prototyping, then port changes to the typed `lib/` modules for the production Next.js UI. The two codebases are currently out of sync — `classifyTestChanges` exists in `lib/versioning.ts` but not here; the Jaccard similarity implementation differs between here and `lib/operations.ts`. Any logic change made here for testing should be manually replicated to the corresponding `lib/` file. The file should not be imported by any Next.js route — its direct Anthropic calls would fail and expose the API key pattern if it were.
