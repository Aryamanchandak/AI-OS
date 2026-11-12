# lib/types.ts — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 108
**Language:** TypeScript

---

## What This File Does (Plain English)

This is the shared type contract for the entire application. It defines every data shape that flows through the system: documents, sections, test cases, assertions, results, versions, and chat messages. No logic lives here — only type declarations and interfaces.

---

## How It Actually Works

### Entry Points

This file is a pure TypeScript module. It has no runtime entry point. Every other file in `lib/` and `app/` imports from it.

### Data Flow

This file produces no output at runtime. It is compiled away. Its role is to constrain what values are legal at compile time.

### State Management

None — this file has no state.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `Mode` | Union type `'prompt' \| 'plan'` — the top-level operational mode of the tool |
| `Iteration` | One chat-driven edit on a section: captures the before/after content, the user's message, and Claude's reasoning |
| `Section` | The core unit of work: an auto-detected chunk of a prompt or plan, with its current content, metadata, and full edit history |
| `AssertionSpec` | A loose bag of optional fields that covers all four assertion types — `mode`, `text`, `schema`, `keys`, `criterion`, `reference`, `similarity_threshold` |
| `Assertion` | One test check: a type discriminator plus the `AssertionSpec` payload |
| `TestCase` | A runnable test: variable substitutions, a user-message context, a list of assertions, and tags |
| `AssertionResult` | The evaluated outcome of one assertion: pass/fail, reasoning text, and a back-reference to the original assertion |
| `TestResult` | The full result of running one `TestCase`: output, error, per-assertion results, latency, and aggregate pass/fail |
| `Conflict` | A cross-section incoherence detected in plan mode: which section, what type (contradiction/redundancy/orphan), and a description |
| `ExtractedContext` | The structured form of the user's project context: goal, tech_stack, constraints, key_decisions, architecture_notes, open_questions |
| `ProjectContext` | Wraps `ExtractedContext` together with the raw text it was derived from |
| `Document` | The top-level container: mode, raw input, sections, and test cases |
| `Version` | A point-in-time snapshot: the full document plus test results (null in plan mode) and conflicts (null in prompt mode) |
| `ChatMessage` | One message in a section-scoped chat thread, with optional structured fields for suggested context updates and clarifying questions |
| `IterationResult` | The structured output of one Claude iteration call, before it gets written back to section state |

### External Dependencies

None at runtime. Imported by `lib/claude.ts`, `lib/operations.ts`, `lib/prompts.ts`, `lib/storage.ts`, `lib/versioning.ts`.

### Error Handling

None — type declarations throw no runtime errors.

---

## Non-Technical Decisions Embedded in the Code

- `AssertionSpec` is a single interface covering all four assertion types rather than a discriminated union per type. Every field is optional, which means the TypeScript compiler cannot catch a `substring` assertion missing its `text` field, or a `semantic` assertion missing its `criterion`. This is a deliberate shortcut that trades type safety for simpler code.
- `Section.history` is typed as `Iteration[]` but nothing in the type system enforces that history entries are immutable or append-only. Any code can rewrite history.
- `Version.testResults` is `Record<string, TestResult> | null` — null is the plan-mode signal. There is no explicit plan-vs-prompt discriminator on `Version` itself, so the null status of these fields carries meaning that is not expressed in the type.
- `ChatMessage` has three optional fields (`suggestedContextUpdate`, `clarifyingQuestion`, `isRewrite`) that were added to carry structured Claude response data through the chat thread. There is no enforcement that these are mutually exclusive.
- `Document` has no `id` field in this definition — but `optimizer.jsx` references `document.id` in comments and `Plan.md` includes `id: string` in the data model diagram. The field is described in the plan but absent from the type declaration.

---

## Honest Gaps and Risks

- `AssertionSpec` is not a discriminated union. A `substring` assertion can legally have `criterion` and `keys` set — the type allows it and runtime code ignores the extras silently.
- `Document` is missing `id` which appears in `Plan.md`'s data model — the spec and the implementation diverge.
- `Version` has no explicit link to which `Document` it belongs to (no `documentId` field). This would become a problem the moment the app supports more than one document.
- `ChatMessage.isRewrite` is defined but unused across the TypeScript modules — it's intended for UI rendering logic that hasn't been written yet.

---

## Developer Notes

All other lib files import types from here using the `@/lib/types` path alias defined in `tsconfig.json`. If you rename or restructure a type here, ripple effects hit every file in `lib/` and potentially `app/page.tsx`. The `AssertionSpec` flat-bag pattern is the most fragile part — any future assertion type will require adding optional fields here rather than creating a clean discriminated union.
