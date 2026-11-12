# Unified Prompt Tester + Plan Optimizer

## 0. What this tool actually is

A way to build on a prompt or plan, speak with it, understand why it works the way it does, tweak it if you want to, and — in the case of a technical plan — dissect why the LLM made each choice so you can ok or override them.

The loop is the same in both modes:

1. Look at a section.
2. Ask why it's there.
3. Decide if you agree.
4. Tweak via chat if you don't.
5. See what shifted as a result.
6. Approve or revert.

That's the whole product. Everything below — auto-section detection, project context, the three-pane view, the diff view, version history, the test suite, the conflict detector — exists to serve that loop. Auto-detection so you don't waste effort splitting. Project context so Claude's "why" answers and rewrites are actually grounded in what you're building. Diff view so step 5 is honest. Version history so step 6 is reversible.

The two modes differ only in what "see what shifted" means in step 5:

- **Prompt mode** uses a test suite. Tests are the proof layer — you don't just trust your edit, the suite tells you what broke or improved.
- **Plan mode** uses cross-section coherence checks. No automated proof exists for a markdown plan, but Claude can flag when an edit in §3 contradicts, duplicates, or orphans something in §5.

In both cases, the goal is the same: turn opaque LLM-generated artifacts into something you can interrogate, understand, and shape with confidence.

---

## 1. Two modes, one tool

- **Prompt mode** — the original prompt unit testing tool. Prompts as functions, tests pin behavior, regressions flagged across versions.
- **Plan mode** — markdown plans, no formal tests, but the same section-based chat-driven iteration with cross-section coherence checks taking the place of regressions.

Both modes share: auto-section detection, project context, three-pane iteration view, diff view, version history, clarifying questions.

The original tool was right about what makes this different from a playground or Promptfoo or Langsmith — the **diff view across versions on the same test case** is the hero. This plan keeps that hero and adds a parallel hero for plans: **cross-section conflict detection** that fires when an edit in §3 contradicts §5.

---

## 2. What the original plan got right (keeping all of it)

Lifting these directly from the existing plan, do not re-litigate:

- Prompt = function. Inputs = templated vars + context. Output = model response. Test case = (input, context, expected behavior).
- Structured prompt editor with named sections (system, role, context, examples, output format, constraints), each independently editable and collapsible.
- Test case definition: input variables, optional context, assertions across four types (structural, substring, semantic via LLM-judge, reference similarity), and tags.
- Run view: actual output + pass/fail per assertion + latency + cost.
- Diff view side-by-side against the previous version's output for the same test case. This is the load-bearing UX.
- Version history snapshots prompt + full test results. Roll back any time.
- Regression flag: a test that passed in N and fails in N+1 is loud.
- LLM-judge as the default assertion in MVP. Forgiving, captures intent, add stricter types later.
- Stack: Next.js + Tailwind, Anthropic API direct, SQLite or JSON for versions.

The judge prompt is itself a prompt and is its own first test subject. Keep that recursive elegance.

---

## 3. What this plan adds

**Plan mode.** A second top-level mode where the user pastes a markdown plan and gets the same section-based iteration UI. No formal test cases (a plan doesn't re-run against assertions), but cross-section conflict detection acts as the equivalent of regression flagging — if §3's content now contradicts §5, that's surfaced as loudly as a broken test.

**Auto-section detection.** The original required the user to decompose the prompt into named sections themselves. This is the "manual splitting" failure mode the user explicitly wants gone. Instead, the user pastes a single blob — prompt or plan — and Claude detects sections itself.

**Project context as a first-class layer.** Tests verify behavior, but they don't tell Claude *what kind of project this prompt is for*. Project context does. It feeds every Claude call (section detection, iteration, judge calls if desired). V1 is manual input; V2 is auto-derived from a local LLM + Watchdog setup.

**Three-pane chat-driven iteration.** The original was edit-then-run-tests. This adds a chat-driven path: click a section, ask Claude in natural language to change it, see the diff, run the tests against the new version. The chat sits alongside the test suite — they're not competing.

**Clarifying questions, always.** Claude asks when context is thin instead of guessing.

---

## 4. The unified data model

```
Document {
  id: string
  mode: 'prompt' | 'plan'
  raw_input: string                    // original blob
  sections: Section[]                  // auto-detected
  context_id: string                   // FK to ProjectContext
  test_suite: TestCase[] | null        // null in plan mode
  versions: Version[]                  // every save
}

Section {
  id: string
  title: string                        // Claude-generated label, user-editable
  kind: string                         // for prompts: 'system' | 'role' | 'context' | 'examples' | 'output_format' | 'constraints' | 'other'
                                       // for plans: 'phase' | 'module' | 'criteria' | 'rationale' | 'other'
  content: string                      // current version of this section
  rationale: string                    // why Claude thinks this section exists
  history: Iteration[]                 // chat-driven edits
}

Iteration {
  timestamp
  user_message: string
  old_content: string
  new_content: string
  claude_reasoning: string
}

TestCase {                             // prompt mode only
  id: string
  name: string
  input_vars: Record<string, string>
  context: string | null
  assertions: Assertion[]
  tags: string[]
}

Assertion {
  type: 'structural' | 'substring' | 'semantic' | 'reference'
  spec: any                            // JSON schema, substring, judge prompt, or reference output
}

Version {
  timestamp
  document_snapshot: Document          // immutable copy
  test_results: TestResult[] | null    // null for plan mode
  diffs_against_prev: SectionDiff[]
  conflicts_detected: Conflict[] | null  // plan mode coherence checks
}

ProjectContext {
  raw_input: string
  extracted: { goal, tech_stack, constraints, key_decisions, architecture_notes, open_questions }
  learnings: Learning[]                // V2-flavored, lightweight in V1
}
```

Plan mode just nulls out the test-suite fields. Same UI shell, same persistence, same export. The sibling-not-replacement design means switching modes feels like a tab change, not a different app.

---

## 5. Auto-section detection (the new shared primitive)

On input — prompt or plan — Claude is called with a system prompt that says: split this into the smallest meaningful sections, label each with a kind from the appropriate enum (prompt or plan), give a short title, return verbatim content, write a one-sentence rationale. JSON output, validated, retry once on parse failure.

For prompts, the kinds map to the original plan's named sections (system, role, context, examples, output format, constraints). For plans, kinds are phase/module/criteria/rationale/other.

The user can override: merge-with-next, split-here. The default split should be good enough that 80% of users accept it untouched. If users override frequently, the splitter prompt needs work — it lives at `prompts/section_splitter_v1.md`, versioned, easy to iterate.

Critically: rationale per section. When the user clicks a section to ask "why is this here," the rationale is what they read. The original plan's structured editor showed sections; this adds *why each section exists* as a first-class affordance.

---

## 6. Project context — V1 manual

Free-text dump, structured by an LLM call into the fields above. Editable. Persists in localStorage per session. Available as a collapsible sidebar.

Every Claude call gets the structured context as system-prompt prefix:
- Section detection (so titles and kinds are project-appropriate)
- Iteration (so rewrites respect the project)
- LLM judge calls (so semantic assertions are evaluated in context — "refuse politely" might mean different things for a kids' app vs. a security tool)
- Conflict detection (so cross-section coherence is judged against project intent)

Mid-session refinement: when Claude's clarifying questions reveal a context gap, the user can either answer in chat (one-time) or update context directly (durable). The UI should make both paths obvious.

---

## 7. Prompt mode specifics

The original plan stays intact. Two additions:

**Auto-detected sections feed the structured editor.** Instead of the user manually labeling system/role/context/etc., the splitter does it. The user can rename or reclassify any section.

**The iteration chat sits in the same three-pane view as plan mode** (see §9). When the user iterates a section via chat, the new section content becomes part of a new version. Tests re-run automatically against that new version. The diff view shows both the section text diff *and* the test-result diff side by side.

This is where prompt mode gets richer than the original spec: the user can now say "make the system prompt more concise" in chat, and immediately see (a) the new system prompt, (b) which tests now pass/fail differently, (c) the regression flags. Three signals from one edit.

The MVP can ship with chat-iteration and tests on the same screen but not yet auto-rerunning — a manual "Run all tests" button is fine for V1 of this enhancement.

---

## 8. Plan mode specifics

No test suite. The replacement is **cross-section conflict detection**.

After every iteration in plan mode, Claude is called with the full document and asked: does this change contradict, duplicate, or undermine any other section? Return a list of `{section_id, type, description}` conflicts.

Types:
- `contradiction` — §3 now says X, §5 still says not-X.
- `redundancy` — §4's content now overlaps §6's significantly.
- `orphan` — §7 references something §3 used to define but no longer does.

Conflicts surface as a non-blocking inline notice, *not* a modal. The user can click each conflict to jump to the affected section. Don't auto-cascade — the user decides whether to update §5 to match §3, or revert §3.

This is the plan-mode hero feature, parallel to the prompt-mode test-regression flag. Both answer the same question — "did my edit break something I can't see right now" — using different machinery.

---

## 9. Three-pane iteration view (shared)

```
┌─────────────────────────────────────────────────────────────────┐
│ Mode: [Prompt | Plan]   Project: <n>   Versions ▾   Export ▾ │
├──────────────┬──────────────────────────┬───────────────────────┤
│              │                          │                       │
│  SECTIONS    │   SECTION CONTENT        │   DIFF / TESTS        │
│              │                          │                       │
│  ▸ §1 sys    │   [rationale shown]      │   Prompt mode:        │
│  ▾ §2 role   │   [section content]      │   • text diff vs prev │
│    selected  │                          │   • test results diff │
│  ▸ §3 ctx    │   [chat input]           │                       │
│  ▸ §4 examp  │                          │   Plan mode:          │
│              │                          │   • text diff vs prev │
│              │                          │   • conflict list     │
└──────────────┴──────────────────────────┴───────────────────────┘
```

Left: section list with kind icon, current title, expand-to-see-rationale.
Middle: selected section content + its rationale + a chat box scoped to it.
Right: diff view. Prompt mode shows section-text diff *and* test-result diff in a tabbed pane. Plan mode shows section-text diff and conflict list.

The chat is the verb. Every chat message produces an iteration: new section content + reasoning + diff + (in prompt mode) re-run tests + (in plan mode) re-run conflict check.

Clarifying questions: when Claude returns `{clarifying_question: "..."}` instead of a rewrite, the question appears in chat and the iteration pauses until the user answers. Answers offer a "save to context" affordance.

---

## 10. The diff view, more carefully

The original plan was right that this is the hero, and it's worth being deliberate about what "diff" means:

**Prompt mode:**
- *Section-text diff* — old vs new for the edited section. Inline highlighting.
- *Test-result diff* — for each test case, three columns: was-passing-now-passing (green), was-passing-now-failing (red, regression flag), was-failing-now-passing (yellow, new pass). Includes per-test actual-output diff so the user can see exactly what shifted.
- *Cost & latency diff* — bumped or dropped?

**Plan mode:**
- *Section-text diff* — same as prompt mode.
- *Conflict diff* — which conflicts existed before this edit, which exist now. New conflicts are loud. Resolved conflicts are quietly celebrated.

In both modes, the diff is *per edit*, but the version history view lets the user diff any two arbitrary versions. The original plan called this out explicitly — "v7 → v8 improved 4 tests, broke 1, no change on 12" — keep that phrasing, it sells the value.

---

## 11. V2 — local LLM + Watchdog (later)

Same as the previous plan, slightly tightened:

- Watchdog watches user-designated project directories. On change, the local LLM updates a per-file/per-folder summary.
- A contextual graph: nodes are files/folders, edges are imports/references/usage/containment. Built from AST + LLM summaries.
- Project context becomes auto-derived. The manual context box becomes optional override.
- Local LLM handles section detection (Claude is overkill for splitting; quality difference doesn't justify the API cost).
- Claude stays on iteration, clarifying questions, semantic assertions, and conflict detection — places where its quality matters.
- Learning loop: when iterations are rejected or modified, the local LLM extracts what was rejected and why. Stored as project-specific learnings, fed into future system prompts.

V1 should stub the local-LLM interface so V2 plugs in without touching the iteration code. A function called `getProjectContext(documentId): ProjectContext` is wired manually in V1 and auto-wired in V2.

---

## 12. Build order

Each step ends in something usable. Steps 1–3 keep the original V1 alive but extend it. Steps 4+ add plan mode and project context.

**Phase A — Extend the existing prompt tester**

1. **Auto-section detection for prompts.** Replace manual section-labeling with a Claude call that splits and labels. Existing structured editor still works, just gets pre-populated. *Test:* paste an unlabeled prompt, verify reasonable section splits.
2. **Project context input.** Free text → LLM extraction → sidebar. Feed context into all existing Claude calls, including the LLM judge. *Test:* same prompt, two different contexts, judge calls produce different verdicts on a context-sensitive test.
3. **Section-scoped chat.** Click a section, type a request, Claude rewrites, tests re-run, diff updates. *Test:* edit a system prompt via chat, see test results shift in the right pane.

After Phase A, the prompt unit testing tool is meaningfully better than the original spec without breaking any of it.

**Phase B — Plan mode**

4. **Mode toggle.** Prompt | Plan switch at the top. Plan mode reuses everything but skips test-suite UI. *Test:* paste a 2000-word plan, verify it splits sensibly.
5. **Cross-section conflict detection.** After every plan-mode iteration, Claude checks for contradictions/redundancies/orphans. Surface as inline notices. *Test:* deliberately contradict a fact across two sections, verify the conflict appears.
6. **Version history for plan mode.** Snapshots the document; right-pane diff shows section text + conflict list. *Test:* iterate a plan ten times, scrub history, verify each version reproducible.

**Phase C — Polish**

7. **Clarifying questions affordance.** Both modes. Question in chat, answer flow, save-to-context offer.
8. **Suggested context updates.** When Claude infers a project-context detail from chat, offer to add it.
9. **Export.** Section-only or full document. Markdown for plans, formatted for prompts. Optional provenance footer listing context used and iteration count.

V1 is shippable after Phase B. Phase C is polish that compounds value but isn't blocking.

---

## 13. What Claude Code should NOT do

- **Don't rewrite the existing JSX.** Extend it. The original test-suite, run-view, version-history pieces stay.
- **Don't build prompt mode and plan mode as separate apps.** One UI, mode toggle. They share 80% of the code path.
- **Don't make the user split sections manually.** If the auto-detector is buggy, fix the prompt — don't fall back to manual.
- **Don't auto-cascade conflict resolution.** Surface conflicts in plan mode; let the user decide. Same posture as not auto-fixing failed tests.
- **Don't add streaming.** Iteration responses are short. Batched is fine. Streaming adds UI complexity that doesn't pay back here.
- **Don't add user accounts or multi-user.** Single-user tool. localStorage + JSON files are enough.
- **Don't build the Watchdog/local-LLM layer in V1.** Stub the `getProjectContext` interface and move on.
- **Don't introduce a backend just for storage.** SQLite via a thin local server is fine if needed; JSON files are fine if not. The test results can balloon — keep storage cheap.

---

## 14. Open questions to surface, not guess

- **Test-rerun cost.** Every chat iteration in prompt mode triggers a test re-run, which is N model calls. For a suite of 20 tests, that's 20 calls per chat message. Acceptable in V1 but add a "manual rerun" toggle and a per-session cost counter.
- **Conflict-detection cost in plan mode.** Every iteration is one extra Claude call. Probably fine. Confirm after a week of use.
- **Section title editing.** User can rename Claude's auto-label inline? Yes, low effort.
- **Persistence across machines.** localStorage is single-machine. Add JSON export/import of full state? V1.5.
- **Concurrent documents.** Multiple prompts/plans open at once? V1 default: one at a time.
- **Mobile.** Three panes don't fit. Desktop-only V1. Defer.
- **Judge prompt as a first-class test subject.** The original plan called this out as pleasingly recursive. Worth surfacing in the UI: "your judge prompt is itself a prompt — open it as a Document?"

---

## 15. Acceptance criteria for V1

The build is done when:

**Prompt mode (extended):**
- Pasting a prompt auto-splits into structured sections without manual labeling.
- Project context, once entered, feeds the section detector, the iteration loop, and the LLM judge.
- Editing a section via chat re-runs the test suite and shows section-text diff + test-result diff side by side.
- Tests that regress are visually loud. Tests that newly pass are visible but quieter.
- Version history snapshots both prompt state and test-result state.

**Plan mode (new):**
- Pasting a plan auto-splits into sections with kinds and rationales.
- Editing a section via chat produces a new version with section-text diff.
- Cross-section conflicts are detected after each edit and surfaced inline.
- Version history works the same as prompt mode minus the test results.

**Shared:**
- Project context is editable, durable across reloads, and visibly feeds into every Claude call.
- Clarifying questions appear when context is thin.
- The existing JSX is extended, not replaced — anything that worked before still works.
- Export produces clean markdown (plans) or formatted prompts (prompts).

---

## 16. Hand-off note for Claude Code

When you start the build session, attach three things:

1. The existing JSX from the original chat (the prompt unit testing tool).
2. The original plan (the document the user pasted in this chat).
3. This plan.

The existing JSX is the trunk. The original plan is the spec for the trunk and must not be undermined. This plan is the spec for what to graft onto the trunk. Where this plan and the original disagree, the original wins for prompt mode mechanics; this plan wins for the new layers (auto-detection, project context, plan mode, chat iteration).

If anything is ambiguous, the right move is to ask the user via §14's open-question pattern — not to guess.