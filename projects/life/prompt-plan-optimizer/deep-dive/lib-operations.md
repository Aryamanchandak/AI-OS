# lib/operations.ts — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 231
**Language:** TypeScript

---

## What This File Does (Plain English)

This is the application's core logic layer. It contains every meaningful action the system can take: parsing a document into sections, extracting project context, iterating on a section via chat, detecting cross-section conflicts, evaluating test assertions, and running a full test case. All functions are pure async — no React state, no DOM, no UI — making them independently testable and portable.

---

## How It Actually Works

### Entry Points

All functions are named exports consumed by:
- `app/page.tsx` — not yet wired (current page is a smoke test only)
- `optimizer.jsx` — contains hand-written inline equivalents; these TypeScript versions are the clean refactor

### Data Flow

```
detectSections(rawInput, mode)
  → callClaudeJSON with PROMPT_SECTION_DETECTOR(mode)
  → receives { sections: [{title, kind, content, rationale}][] }
  → assigns stable ids (s1, s2, ...) and initialises empty history[]
  → returns Section[]

extractContext(rawText)
  → callClaudeJSON with PROMPT_CONTEXT_EXTRACTOR
  → receives ExtractedContext object
  → wraps it with { raw: rawText, extracted }
  → returns ProjectContext

iterateSection({mode, section, fullDocument, projectContext, chatHistory, userMessage})
  → callClaudeJSON with PROMPT_ITERATION(...)
  → receives { rewritten_content, reasoning, clarifying_question, suggested_context_update }
  → remaps to camelCase IterationResult
  → returns IterationResult

detectConflicts({sections, editedSectionId, projectContext})
  → callClaudeJSON with PROMPT_CONFLICT_DETECTOR(...)
  → receives { conflicts: Conflict[] }
  → returns conflicts array (empty array if null/missing)

renderTemplate(template, vars)
  → replaces {{varName}} tokens with values from vars map
  → leaves unresolved tokens as-is ({{varName}})
  → returns string

evaluateAssertion({assertion, output, projectContext})
  → dispatches on assertion.type:
     'substring'  → local string check (output.includes)
     'structural' → local JSON parse + optional key check
     'semantic'   → callClaudeJSON with PROMPT_LLM_JUDGE
     'reference'  → local Jaccard similarity computation
  → returns { passed: boolean, reasoning: string }

runTest({promptDocument, testCase, projectContext})
  → joins all section contents with '\n\n' as system prompt
  → renderTemplate on combined prompt with testCase.inputVars
  → callClaude with rendered prompt as system, testCase.context as user message
  → for each assertion: evaluateAssertion(...)  [sequential, not parallel]
  → returns TestResult with all assertion results + latency + aggregate pass/fail
```

### State Management

No module-level state. All functions receive their inputs as arguments and return results. State is managed by the UI layer.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `detectSections()` | Calls Claude to split a raw text blob into structured sections; assigns client-side IDs |
| `extractContext()` | Calls Claude to parse a freeform project dump into a structured `ProjectContext` object |
| `iterateSection()` | Calls Claude to respond to a user's chat message about a section; returns rewritten content plus reasoning and optional follow-up question |
| `detectConflicts()` | Calls Claude to find contradictions, redundancies, and orphan references across sections after an edit |
| `renderTemplate()` | Pure string interpolation: replaces `{{token}}` placeholders in a prompt with values from a vars map |
| `evaluateAssertion()` | Routes one assertion to the correct evaluation strategy (local check or Claude call); returns pass/fail and reasoning |
| `runTest()` | Composes sections into a full prompt, runs it against Claude, evaluates all assertions, returns aggregated `TestResult` |

### External Dependencies

- `lib/claude.ts` — `callClaude`, `callClaudeJSON`
- `lib/prompts.ts` — all five prompt constructors
- `lib/types.ts` — all type imports

### Error Handling

- `runTest` catches errors from the Claude call and returns a `TestResult` with `passed: false`, `error: e.message`, and empty `assertions[]` — this is the only explicit error boundary in the file
- All other functions (`detectSections`, `extractContext`, `iterateSection`, `detectConflicts`) do not catch errors — they propagate up to the caller
- `evaluateAssertion` `structural` branch catches `JSON.parse` errors and returns `{passed: false, reasoning: 'Output is not valid JSON'}`
- `evaluateAssertion` `default` branch handles unknown assertion types with a failed result and a message naming the unknown type

---

## Non-Technical Decisions Embedded in the Code

- **Section IDs are client-side assigned** as `s1`, `s2`, etc. based on array index after the Claude call returns. If Claude returns sections in a different order than the user expects, the IDs are still monotonically assigned — there is no stable ID derived from content.
- **`iterateSection` passes `projectContext?.extracted ?? null`** — if `projectContext` exists but `extracted` is undefined, null is passed. The prompt handles null context with a fallback message.
- **`detectConflicts`**: the `userMessage` is hardcoded as `'Check for conflicts now.'` — the function never uses any real user input; the message is a fixed trigger phrase.
- **`evaluateAssertion` substring case**: uses `assertion.spec.text ?? ''`. An empty-string `text` value means `output.includes('')` which is always true. A `must_include` assertion with no text always passes silently.
- **`evaluateAssertion` reference case** uses a Jaccard similarity on word tokens (lowercased word regex). This is described in `optimizer.jsx` as "Simple word-overlap similarity for V1. Replace with embedding similarity later." — it is an acknowledged placeholder, not a final implementation.
- **Assertions in `runTest` are evaluated sequentially** in a for-loop, not with `Promise.all`. For a test case with multiple `semantic` assertions, each triggers a separate Claude call and each must complete before the next begins. This is a significant latency multiplier.
- **`renderTemplate` leaves unresolved tokens unchanged** rather than throwing or substituting empty string. A prompt with `{{name}}` where `inputVars` has no `name` key will silently send `{{name}}` to Claude.

---

## Honest Gaps and Risks

- **Substring assertion always passes when `spec.text` is missing** — `output.includes('')` is always `true`, so a `must_include` assertion with no `text` field passes every run. This is a silent always-pass bug.
- **Serial assertion evaluation** — N semantic assertions = N sequential Claude calls per test run. For a test suite with multiple tests each having multiple semantic assertions, this is very slow and very expensive.
- **No validation of Claude's section count** — `detectSections` returns whatever Claude returns. If Claude merges everything into one section or splits into dozens, the caller gets that result with no warning.
- **`detectConflicts` always returns an empty array if `result.conflicts` is null** — if Claude returns `{}` or an unexpected shape, `result.conflicts || []` silently yields no conflicts.
- **`evaluateAssertion` reference type has a subtle difference from `optimizer.jsx`** — the TypeScript version computes `intersection` over `aArr` (an array, not a Set), while `optimizer.jsx` computes it over a Set. The TypeScript version double-counts duplicate words in `output`, slightly inflating Jaccard similarity. The JSX version deduplicates both sides first.
- **No retry or fallback on `runTest` Claude call** — a transient Anthropic error on the test run itself returns a failed `TestResult`. The user sees a test failure that is actually an API error.

---

## Developer Notes

This file is the intended production version of the logic that is duplicated inline in `optimizer.jsx`. The two are not identical — the TypeScript version routes through the `/api/claude` proxy while `optimizer.jsx` calls Anthropic directly from the browser (which requires exposing the API key to the client). Any logic changes made to `optimizer.jsx` for prototyping need to be manually ported here. The `evaluateAssertion` reference branch Jaccard implementation silently diverges from the JSX version — see risk above.
