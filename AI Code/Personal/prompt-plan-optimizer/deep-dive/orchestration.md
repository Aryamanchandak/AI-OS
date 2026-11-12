# System Orchestration — How It All Fits Together

**Last updated:** 2026-05-10

---

## System Overview

This is a prompt and plan iteration tool. The user pastes a prompt or a technical plan, and the system auto-splits it into sections using Claude. The user then chats with individual sections — asking why they exist, or requesting changes — and the tool tracks diffs, runs tests (for prompts), and detects cross-section conflicts (for plans). The project is a Next.js 14 application that is mid-refactor: a working prototype (`optimizer.jsx`) and a clean modular backend (`lib/`) coexist, but they are not yet wired together into a live UI.

---

## Component Map

| File | Role |
|---|---|
| `app/api/claude/route.ts` | Server-side proxy that forwards requests to Anthropic; keeps the API key server-only |
| `lib/types.ts` | Shared TypeScript contract — all data shapes used across the system |
| `lib/claude.ts` | Client-side API helper; routes all Claude calls through `/api/claude` |
| `lib/prompts.ts` | All five system prompts: section detector, context extractor, iteration, conflict detector, LLM judge |
| `lib/operations.ts` | Core logic layer: section detection, context extraction, iteration, conflict detection, assertion evaluation, test running |
| `lib/diff.ts` | LCS-based line diff algorithm |
| `lib/versioning.ts` | Immutable version snapshot creation and test-change classification |
| `lib/storage.ts` | localStorage read/write layer for documents, project context, and version history |
| `app/page.tsx` | Temporary smoke test for the API proxy only; not the real UI |
| `app/layout.tsx` | HTML shell with font loading and global metadata |
| `app/globals.css` | Tailwind directives and color token definitions |
| `optimizer.jsx` | The original monolith: inline duplicates of all lib logic plus a working scaffolding UI; not routed by Next.js; reference prototype only |
| `package.json` | Dependencies and npm scripts |
| `tsconfig.json` | TypeScript config including `@/*` path alias |
| `tailwind.config.ts` | Tailwind content paths and theme extensions |
| `postcss.config.mjs` | PostCSS with Tailwind plugin |
| `.eslintrc.json` | ESLint extending Next.js and TypeScript rulesets |

---

## Data and Control Flow

### The Intended Production Flow (not yet live)

This describes how the system is designed to work once Phase B UI is built and wired to `lib/`:

```
1. User opens the app (/)
   → app/page.tsx renders (currently: smoke test only)
   → lib/storage.ts loadDocument() / loadContext() / loadVersions() on mount
   → If no stored document: show onboarding UI

2. User pastes project context text
   → lib/operations.ts extractContext(rawText)
   → lib/claude.ts callClaudeJSON({ system: PROMPT_CONTEXT_EXTRACTOR, ... })
   → POST /api/claude  →  app/api/claude/route.ts  →  Anthropic API
   → Returns ExtractedContext  →  stored in React state + lib/storage.ts saveContext()

3. User pastes prompt or plan text + clicks "Analyze"
   → lib/operations.ts detectSections(rawInput, mode)
   → lib/claude.ts callClaudeJSON({ system: PROMPT_SECTION_DETECTOR(mode), ... })
   → POST /api/claude  →  Anthropic API
   → Returns Section[]  →  Document assembled  →  lib/storage.ts saveDocument()

4. User selects a section and sends a chat message
   → lib/operations.ts iterateSection({ mode, section, fullDocument, projectContext, chatHistory, userMessage })
   → lib/claude.ts callClaudeJSON({ system: PROMPT_ITERATION(...), ... })
   → POST /api/claude  →  Anthropic API
   → Returns { rewritten_content, reasoning, clarifying_question, suggested_context_update }
   → If content changed: section.history updated, new version snapshotted
   → lib/versioning.ts snapshotDocument(document, testResults, conflicts)
   → lib/storage.ts saveVersions(versions)

5a. Prompt mode only: run tests
   → lib/operations.ts runTest({ promptDocument, testCase, projectContext })
   → Joins section content → renders {{vars}} via renderTemplate()
   → lib/claude.ts callClaude({ system: renderedPrompt, userMessage: testCase.context })
   → POST /api/claude  →  Anthropic API
   → For each assertion: lib/operations.ts evaluateAssertion()
       - substring/structural: local evaluation (no API call)
       - semantic: lib/claude.ts callClaudeJSON({ system: PROMPT_LLM_JUDGE(...) })  →  API
       - reference: local Jaccard similarity
   → Returns TestResult  →  stored in testResults state

5b. Plan mode only: detect conflicts after section edit
   → lib/operations.ts detectConflicts({ sections, editedSectionId, projectContext })
   → lib/claude.ts callClaudeJSON({ system: PROMPT_CONFLICT_DETECTOR(...), ... })
   → POST /api/claude  →  Anthropic API
   → Returns Conflict[]  →  stored in conflicts state

6. User views diff of last section edit
   → lib/diff.ts diffLines(section.history[-1].oldContent, section.history[-1].newContent)
   → Returns DiffLine[]  →  rendered in right pane

7. User rolls back to a previous version
   → lib/versioning.ts (snapshot was already stored; rollback is UI state restoration)
   → lib/storage.ts loadVersions() on reload
```

### The Current Live Flow (what actually runs today)

```
1. User opens http://localhost:3000
   → app/page.tsx renders the smoke test page

2. User clicks "Test backend"
   → Inline fetch to POST /api/claude
   → app/api/claude/route.ts receives it
   → Forwards to Anthropic API using process.env.ANTHROPIC_API_KEY
   → Response displayed as text or error

   None of lib/operations.ts, lib/prompts.ts, lib/diff.ts, lib/versioning.ts,
   lib/storage.ts, or lib/types.ts is called by the live application.
```

---

## Mode / State Machine

The application has two operating modes controlled by a `mode: 'prompt' | 'plan'` value:

| Mode | Section kinds | Test suite | Conflict detection |
|---|---|---|---|
| `'prompt'` | system, role, context, examples, output_format, constraints, other | Active — test cases run against Claude | Not used |
| `'plan'` | phase, module, criteria, rationale, overview, other | Not used | Active — runs after every section edit |

Mode determines which prompts are used (`PROMPT_SECTION_DETECTOR` is parameterized on mode), which UI panels are shown (tests vs conflicts), and which post-edit side effects fire (`runTest` vs `detectConflicts`).

In `optimizer.jsx`, mode can be changed while a document is loaded. Doing so does not re-analyze the document with the new mode's section vocabulary — sections keep their old kind labels.

---

## Key Integration Points

### The Proxy as the Single Communication Gate
Every Claude call in the TypeScript modules goes through `/api/claude`. The API key never leaves the server. Any change to the Anthropic API version, authentication, or rate-limiting strategy is a change to `app/api/claude/route.ts` alone.

### lib/claude.ts → lib/operations.ts (tight coupling)
`callClaude` and `callClaudeJSON` are the only functions in `lib/claude.ts`. Every function in `lib/operations.ts` calls one of them. If you change the response format of these functions (e.g., returning a structured object instead of a raw string), every operation breaks.

### lib/prompts.ts → lib/operations.ts → lib/types.ts (triple dependency)
A change to a prompt schema in `lib/prompts.ts` must be mirrored in the TypeScript types in `lib/types.ts` and the destructuring code in `lib/operations.ts`. There is no shared schema definition — these three files are implicitly coupled and can drift.

### optimizer.jsx vs lib/ (parallel implementations)
`optimizer.jsx` contains inline duplicates of every `lib/` module's logic. They are not bit-for-bit identical:
- `callClaude` in `optimizer.jsx` calls Anthropic directly (broken in browser without CORS/key); `lib/claude.ts` calls `/api/claude`
- Jaccard similarity in `optimizer.jsx` deduplicates tokens (Set); `lib/operations.ts` does not (Array)
- `classifyTestChanges` exists in `lib/versioning.ts` but has no equivalent in `optimizer.jsx`

Changes made to `optimizer.jsx` for prototyping must be manually ported to the appropriate `lib/` file.

### lib/storage.ts (unused by live application)
`lib/storage.ts` is complete and correct but is not called by `app/page.tsx`. Persistence is implemented but not wired up. The intended integration point is the UI layer that will replace `app/page.tsx` in Phase B.

---

## External Dependencies (System-Level)

| Dependency | Where | What it does |
|---|---|---|
| `https://api.anthropic.com/v1/messages` | `app/api/claude/route.ts` | The Anthropic Messages API; all Claude calls ultimately hit this |
| `process.env.ANTHROPIC_API_KEY` | `app/api/claude/route.ts` | The secret API key; must be set in `.env.local` for dev |
| `localStorage` | `lib/storage.ts` | Browser-only; stores document, context, and version history across reloads |
| `navigator.clipboard` | `optimizer.jsx` (`handleExport`) | Browser clipboard API for export; requires HTTPS and user permission |

---

## Known Architectural Risks

### 1. No live UI — the lib modules are untested end-to-end
The TypeScript `lib/` modules are written and type-check, but no live page calls them. Their correctness in production is unknown until Phase B is built and wired.

### 2. Stale conflict snapshot bug in optimizer.jsx
In `handleSendMessage`, the version snapshot captures the pre-edit `conflicts` state, not the freshly detected `newConflicts`. This means the version history in plan mode stores one-edit-stale conflict data. The bug is in `optimizer.jsx` only; `lib/versioning.ts` itself is not buggy — the caller is.

### 3. Three files must change together for any prompt schema change
`lib/prompts.ts`, `lib/types.ts`, and `lib/operations.ts` are implicitly coupled through JSON schemas described as template strings. TypeScript provides no safety net — the coupling is invisible at compile time.

### 4. Silent data loss on localStorage corruption
`lib/storage.ts` swallows all parse errors. If stored JSON becomes invalid, the user loses all work with no warning and no recovery path.

### 5. The proxy is unauthenticated
`app/api/claude/route.ts` has no authentication. In a deployed environment, any visitor can make Anthropic API calls billed to the account. This is intentional for a single-user local tool but is a critical gap before any shared deployment.

### 6. Semantic assertions scale poorly
Running a test case with N semantic assertions makes N sequential Claude API calls via the for-loop in `runTest`. For a suite of 10 test cases each with 3 semantic assertions, a single "Run all tests" triggers 30 serial Claude calls. The `Plan.md` explicitly flags this as a cost concern.

### 7. Mode switching does not re-analyze
Switching mode while a document is loaded does not re-run section detection. Sections analyzed as `'prompt'` keep kind labels like `system`, `role`, `context` even if the user switches to `plan` mode — where the kind vocabulary is `phase`, `module`, `criteria`.
