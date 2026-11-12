// =====================================================================
// PROMPT + PLAN OPTIMIZER — V1 (manual context, Claude as backend)
// =====================================================================
// This file is structured backend-first. Top half is pure logic
// (prompts, API helpers, diff, assertion runners). Bottom half is a
// minimal scaffolding UI to exercise that logic. Lift the top half
// into your real codebase when you build the production UI.
// =====================================================================
//
// =====================================================================
// UI PLAN — for wiring into the real production interface
// =====================================================================
//
// The backend below is UI-agnostic. Every operation is a pure async
// function. The UI plan that follows describes how those operations
// should connect to a polished interface. Match this to whatever
// design system you're using.
//
// ---------------------------------------------------------------------
// THE PURPOSE (must be visible in the UI itself)
// ---------------------------------------------------------------------
// This tool lets the user build on a prompt or plan, speak with it,
// understand why it works the way it does, tweak it if they want to,
// and — for technical plans — dissect why the LLM made each choice
// so they can ok or override them. The six-step loop is:
//
//   1. Look at a section
//   2. Ask why it's there
//   3. Decide if you agree
//   4. Tweak via chat if you don't
//   5. See what shifted as a result
//   6. Approve or revert
//
// The UI's job is to make this loop fast and obvious. Every screen
// should serve one of those six steps without ceremony.
//
// ---------------------------------------------------------------------
// SCREEN 1 — ONBOARDING / NEW DOCUMENT
// ---------------------------------------------------------------------
// Shown when no document is loaded. Two top-bar buttons toggle Prompt
// vs Plan mode. Below the toggle, two stacked input regions:
//
//   Region A — PROJECT CONTEXT
//     One large textarea. Placeholder: "Dump anything — bullets,
//     ramblings, half a tech spec." A single primary button:
//     "Extract context." After extraction, render the parsed JSON in
//     a collapsible card directly below, with each field
//     individually editable inline (don't make the user re-paste).
//     The raw dump stays accessible as a "View raw" toggle.
//
//   Region B — DOCUMENT INPUT
//     Another large textarea. Placeholder differs by mode:
//     "Paste a full prompt — sections will be auto-detected" or
//     "Paste a markdown plan — sections will be auto-detected".
//     Single primary button: "Analyze and split into sections."
//
// Backend wiring: extractContext(rawText) for Region A,
// detectSections(rawInput, mode) for Region B.
//
// Once both are populated and the user clicks Analyze, transition
// to Screen 2.
//
// ---------------------------------------------------------------------
// SCREEN 2 — THREE-PANE WORKING VIEW (the main surface)
// ---------------------------------------------------------------------
// Persistent top bar:
//   - Mode pill (Prompt | Plan, but locked once a doc is loaded)
//   - Project name (editable inline)
//   - Versions dropdown (lists v1, v2, ... with timestamp; clicking
//     one previews; a "Roll back" affordance commits)
//   - Export dropdown (Section only | Full document; markdown or
//     plain text)
//   - In Prompt mode only: "+ Test" and "Run all tests" buttons
//   - Status indicator on the right (busy spinner / version count)
//
// Body grid: 3 columns. Recommended widths: 240px / 1fr / 1fr.
// On narrow screens (<1100px), collapse the right pane into a
// bottom drawer with a tab toggle.
//
// LEFT PANE — SECTION LIST + VERSION HISTORY
//   Top half: section list. Each row shows:
//     - Section number (§1, §2, ...)
//     - Kind tag (small uppercase: SYSTEM, ROLE, CONTEXT, PHASE, etc.)
//     - Title (Claude-generated, editable inline by double-click)
//     - Edit count badge if section.history.length > 0
//   Selected row highlights with an accent border.
//   On hover, an "i" icon reveals the rationale as a tooltip.
//   Override affordances on each row (small icons): merge-with-next,
//   split-here, delete, rename.
//
//   Bottom half: version history. Each row is "v3 · 4:21 PM · 2 edits".
//   Clicking previews the version (read-only mode); a Roll Back button
//   appears at the top of the body to commit.
//
// MIDDLE PANE — SECTION CONTENT + CHAT
//   Top: kind tag, title (h2), rationale (italic gray, dismissable).
//   Middle: section content rendered with proper monospace for prompts,
//   markdown rendering for plans. Scrollable. Read-only.
//   Bottom: chat thread for THIS section only.
//     - User messages right-aligned, Claude messages left-aligned
//     - Reasoning is displayed as the main text of Claude messages
//     - When Claude returns a clarifying_question, render it as a
//       distinct prompt-card with an answer textarea below
//     - When Claude returns a suggested_context_update, render it as
//       a small chip: "+ Add to context: <update>" (clickable)
//   Input: textarea + Send button (Cmd+Enter shortcut). Placeholder:
//   "Ask why this section is the way it is, or request a change..."
//
// RIGHT PANE — DIFF + (TESTS or CONFLICTS) + CONTEXT
//   Sub-section A: DIFF
//     For the most recent edit on the selected section, render
//     diffLines() output with green/red highlighting. Toggle at the
//     top: "Section diff" | "Whole document diff".
//   Sub-section B (Prompt mode): TEST RESULTS
//     For each test case:
//       - Test name + status badge (pass/fail/not-run)
//       - Latency in ms
//       - Per-assertion breakdown: ✓/✗ + assertion type + reasoning
//       - When a test goes from pass to fail (regression), show a
//         loud "REGRESSION" badge in red. When a test goes from fail
//         to pass, show a quieter "NEW PASS" badge in yellow.
//       - Click a test to expand: see actual output diffed against
//         the previous version's output for the same test case.
//         THIS IS THE HERO INTERACTION — the user changed one word
//         and can see exactly how each test's output drifted.
//   Sub-section B (Plan mode): CONFLICTS
//     For each conflict:
//       - Type pill (CONTRADICTION / REDUNDANCY / ORPHAN)
//       - "§3 conflicts with §5" — clicking jumps to the named section
//       - Description sentence
//     Conflicts are loud (red border). When the conflict list shrinks
//     after an edit, the resolved conflict animates out quietly.
//   Sub-section C: PROJECT CONTEXT
//     Collapsed by default. Shows the structured fields. Each field
//     is editable inline. Manual updates re-extract on save.
//
// ---------------------------------------------------------------------
// CHAT MESSAGE TYPES (middle pane)
// ---------------------------------------------------------------------
// Three distinct rendering shapes:
//
//   USER MESSAGE
//     Right-aligned, accent background, plain text.
//
//   CLAUDE EXPLANATION (no rewrite, just answers a "why" question)
//     Left-aligned, neutral background. Just the reasoning text.
//     No diff, no edit indicator.
//
//   CLAUDE EDIT (rewrote the section)
//     Left-aligned, neutral background, with a small "Edited section"
//     header. Reasoning text. A small "View diff →" link that scrolls
//     the right pane to the diff for this iteration. An "Undo this
//     edit" button (reverts the section to the prior history entry).
//
//   CLAUDE CLARIFYING QUESTION
//     Distinct card style — yellow border, "Claude is asking" header.
//     Question text. Inline answer textarea + "Send answer" button.
//     The chat is paused (greyed-out send button on the main input)
//     until the user answers or dismisses.
//
//   CONTEXT UPDATE SUGGESTION (footer of any Claude message)
//     Small chip below the message: "+ Add to context: <update>".
//     One click adds it; chip fades out after.
//
// ---------------------------------------------------------------------
// TEST CASE EDITOR (Prompt mode only)
// ---------------------------------------------------------------------
// Triggered by the "+ Test" top-bar button or by clicking a test in
// the right pane. Opens as a modal or side-drawer. Fields:
//
//   - Name (string)
//   - Tags (chips, multi-add)
//   - Input variables (key-value rows; keys match {{var}} placeholders
//     in the prompt)
//   - Context (textarea — the user message that follows the prompt)
//   - Assertions (list, each with a type dropdown):
//       * substring: mode (must_include | must_not_include) + text
//       * structural: schema (json | json_with_keys) + optional keys
//       * semantic: criterion (textarea — natural language description)
//       * reference: reference text + similarity threshold (0.0-1.0)
//
// Each assertion row has a delete button. Below the list: "+ Add
// assertion" with the type dropdown.
//
// On save, the test case is added to document.testCases. Clicking
// "Run all tests" in the top bar runs every test and updates
// testResults state.
//
// ---------------------------------------------------------------------
// DIFF VIEW DETAILS
// ---------------------------------------------------------------------
// Use diffLines() output. Recommended rendering:
//   - Equal lines: muted color, single space prefix
//   - Added lines: green background, "+ " prefix
//   - Removed lines: red background, "- " prefix
//   - Render in monospace, line-numbered if helpful
//
// Two view modes:
//   1. Section diff (default): old content vs new content for the
//      most recent edit on the selected section.
//   2. Document diff: full old document vs full new document for the
//      currently-selected version vs previous version.
//
// In Prompt mode, also offer a TEST OUTPUT DIFF view: for a single
// test case, show how its actual output changed between two versions
// of the prompt. This is the original plan's hero interaction.
//
// ---------------------------------------------------------------------
// VERSION HISTORY UX
// ---------------------------------------------------------------------
// Every save (every section edit that produces new content) creates
// a version. Each version stores the full document, test results
// (prompt mode), and conflicts (plan mode).
//
// Browsing: clicking a version in the left pane enters READ-ONLY
// PREVIEW MODE. The chat input is disabled, sections show the version's
// content, the right pane shows that version's tests/conflicts. A
// banner at the top: "Previewing v3 — Roll back | Return to current".
//
// Comparing: shift-click two versions in the version list to enter
// COMPARE MODE. Right pane shows: "v3 → v7 — 4 tests improved, 1
// broken, 12 unchanged". Each test/section row is clickable for
// the detailed diff.
//
// ---------------------------------------------------------------------
// EXPORT
// ---------------------------------------------------------------------
// Two scopes:
//   - Section only: just the current selected section's content
//   - Full document: all sections concatenated in order
//
// Two formats:
//   - Markdown (sections become ## headers using their titles)
//   - Plain text (sections joined with double newlines, no headers)
//
// Optional provenance footer (off by default, toggleable in settings):
//   - Project context used
//   - Version number
//   - Per-section iteration count
//
// ---------------------------------------------------------------------
// NICETIES TO ADD WHEN POLISHING
// ---------------------------------------------------------------------
//   - Cmd+K command palette: "Run tests", "New section", "Toggle
//     mode", "Export full document", "Roll back to v...", "Add to
//     context: ...". Power-user superpower.
//   - Per-section keyboard shortcuts: J/K to navigate sections,
//     Enter to focus chat input, Cmd+Z to undo last edit on this
//     section.
//   - Loading states that name what's happening: "Asking Claude to
//     rewrite §3..." not just a spinner.
//   - Cost counter in the top bar (estimated cents per session).
//     Particularly important once test re-runs become automatic.
//   - Empty states with example content. New users should see a
//     pre-loaded example prompt + tests so they can poke without
//     typing.
//
// ---------------------------------------------------------------------
// WHAT NOT TO BUILD IN THE UI
// ---------------------------------------------------------------------
//   - No multi-user features. Single user, single machine.
//   - No streaming output. Iteration responses are short enough that
//     batched is fine and the UI stays simpler.
//   - No auto-cascade for cross-section conflicts. Always surface,
//     never auto-fix. The user decides.
//   - No mobile layout for V1. Desktop-only.
//   - No section manual-splitting fallback. If the auto-detector is
//     bad, fix the prompt — don't put a "manual split" mode in the UI.
//
// ---------------------------------------------------------------------
// STATE SHAPE TO MIRROR (already implemented in the scaffold UI below)
// ---------------------------------------------------------------------
//   mode:               'prompt' | 'plan'
//   projectContext:     { raw, extracted } | null
//   document:           { sections, testCases } | null
//   selectedSectionId:  string | null
//   chatBySection:      { [sectionId]: [{role, text, ...}] }
//   conflicts:          [{section_id, type, description}]
//   testResults:        { [testCaseId]: TestResult }
//   versions:           [{timestamp, document, testResults, conflicts}]
//   busy:               string  // current operation label
//   error:              string
//
// Backend operations to call:
//   detectSections(rawInput, mode)
//   extractContext(rawText)
//   iterateSection({mode, section, fullDocument, projectContext,
//                   chatHistory, userMessage})
//   detectConflicts({sections, editedSectionId, projectContext})
//   runTest({promptDocument, testCase, projectContext})
//   diffLines(oldText, newText)
//   snapshotDocument(document, testResults, conflicts)
//
// =====================================================================

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';

// ---------------------------------------------------------------------
// 1. CLAUDE API HELPERS
// ---------------------------------------------------------------------
// All Claude calls go through these two functions. callClaudeJSON adds
// JSON parsing with one retry on parse failure — important because the
// section detector and iteration calls return structured data and a
// single bad response shouldn't kill the whole flow.
// ---------------------------------------------------------------------

const MODEL = "claude-sonnet-4-20250514";

async function callClaude({ system, userMessage, maxTokens = 2000 }) {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: maxTokens,
      system,
      messages: [{ role: "user", content: userMessage }],
    }),
  });
  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Claude API error (${response.status}): ${errText}`);
  }
  const data = await response.json();
  const textBlock = data.content?.find?.(b => b.type === 'text');
  return textBlock?.text || '';
}

async function callClaudeJSON({ system, userMessage, maxTokens = 2000 }) {
  const tryParse = (text) => {
    // Strip ```json fences if present
    const cleaned = text
      .replace(/^```(?:json)?\s*/i, '')
      .replace(/\s*```$/, '')
      .trim();
    return JSON.parse(cleaned);
  };

  const text = await callClaude({ system, userMessage, maxTokens });
  try {
    return tryParse(text);
  } catch (e) {
    // One retry with explicit instruction
    const retryText = await callClaude({
      system: system + "\n\nIMPORTANT: Respond with ONLY valid JSON. No prose, no markdown fences, no preamble.",
      userMessage,
      maxTokens,
    });
    try {
      return tryParse(retryText);
    } catch (e2) {
      throw new Error(`Failed to parse JSON after retry. Raw output:\n${retryText.slice(0, 500)}`);
    }
  }
}

// ---------------------------------------------------------------------
// 2. PROMPTS
// ---------------------------------------------------------------------
// Every prompt is a constant or a function returning a string. Keep them
// here so they're easy to find, version, and tune. Each one specifies
// strict JSON schemas — Claude is reliable about these but not perfect,
// hence the retry in callClaudeJSON.
// ---------------------------------------------------------------------

const PROMPT_SECTION_DETECTOR = (mode) => `You are splitting a ${mode === 'prompt' ? 'prompt' : 'technical plan written in markdown'} into its constituent sections.

Return ONLY valid JSON with this exact schema:
{
  "sections": [
    {
      "title": "short label, 2-6 words",
      "kind": "${mode === 'prompt' ? "one of: system | role | context | examples | output_format | constraints | other" : "one of: phase | module | criteria | rationale | overview | other"}",
      "content": "VERBATIM text from the input — do not paraphrase or summarize",
      "rationale": "one sentence explaining why this section exists as a distinct unit"
    }
  ]
}

Splitting rules:
- Prefer splitting on existing markdown headers (# / ## / ###) when present.
- Otherwise split on semantic boundaries: role changes, topic shifts, phase transitions.
- Each section should be 1-3 paragraphs typically. Merge tiny fragments. Split overly long sections at natural sub-topics.
- The "content" field MUST contain the original text exactly as written. Do not edit, clean up, or rephrase.
- The "rationale" is what the user reads when they ask "why is this section here?" — make it about purpose, not just description.
- 80% of users should accept your splits without reorganizing. Aim for clarity over cleverness.

If the input has no clear structure, fall back to one section with kind="other".`;

const PROMPT_CONTEXT_EXTRACTOR = `You are extracting structured project context from a user's freeform dump. The dump may be rambling, structured, half-formed, or anything in between.

Return ONLY valid JSON with this exact schema:
{
  "goal": "one or two sentences on what is being built and why",
  "tech_stack": ["array", "of", "technologies"],
  "constraints": ["array of constraints — deadlines, infra limits, things off-limits, team size"],
  "key_decisions": ["decisions already made that should not be re-litigated"],
  "architecture_notes": "any load-bearing architectural notes, or empty string",
  "open_questions": ["things the user explicitly hasn't decided yet"]
}

Rules:
- Use empty array or empty string for fields with no info. Do not invent.
- "key_decisions" captures things the user has settled on (e.g., "using Postgres not SQLite", "FSRS over SM-2"). These matter because future iterations should respect them.
- "open_questions" captures things the user is still figuring out. Future iterations may revisit these.
- Be terse. This is going into a system prompt, not a report.`;

const PROMPT_ITERATION = ({ mode, projectContext, fullDocument, currentSection, chatHistory, userMessage }) => `You are helping a user iterate on one section of a ${mode === 'prompt' ? 'prompt' : 'plan'}. The user has clicked into this section and is asking you to explain it, change it, or push back on it.

PROJECT CONTEXT:
${projectContext ? JSON.stringify(projectContext, null, 2) : '(no context provided yet — be especially willing to ask clarifying questions)'}

FULL DOCUMENT (for cross-section awareness):
${fullDocument}

CURRENT SECTION YOU'RE WORKING ON:
Title: ${currentSection.title}
Kind: ${currentSection.kind}
Rationale: ${currentSection.rationale}
Content:
"""
${currentSection.content}
"""

CHAT HISTORY FOR THIS SECTION:
${chatHistory.length === 0 ? '(this is the first message)' : chatHistory.map(m => `${m.role}: ${m.text}`).join('\n')}

USER'S CURRENT MESSAGE:
${userMessage}

Return ONLY valid JSON with this exact schema:
{
  "rewritten_content": "the new content for this section — or unchanged if you're asking a question or just explaining",
  "reasoning": "your reasoning for this response, in plain English. If explaining why the section is the way it is, put that explanation here. If rewriting, explain what you changed and why.",
  "clarifying_question": "a question to ask the user, OR null if you don't need to ask anything",
  "suggested_context_update": "a project-context update inferred from the chat (e.g., 'tech_stack: add Postgres'), OR null"
}

Behavior rules:
- If the user is asking WHY a section is the way it is, put your explanation in "reasoning" and leave "rewritten_content" unchanged.
- If the user is asking you to change the section, rewrite it in "rewritten_content" and explain the change in "reasoning".
- If the user's request is ambiguous OR you lack project context to do it well, ASK A QUESTION via "clarifying_question" and leave "rewritten_content" unchanged. Always prefer asking over guessing.
- If the chat reveals a project fact worth remembering ("we're using X", "we decided Y"), surface it via "suggested_context_update".
- Stay in scope. Don't rewrite other sections — only this one.
- Don't editorialize. The user wants help, not lectures.`;

const PROMPT_CONFLICT_DETECTOR = ({ sections, editedSectionId, projectContext }) => `You are checking a plan for cross-section conflicts after a recent edit. The user just edited the section marked [EDITED] below. Your job is to flag whether that edit creates contradictions, redundancies, or orphan references with other sections.

PROJECT CONTEXT:
${projectContext ? JSON.stringify(projectContext, null, 2) : '(none)'}

SECTIONS:
${sections.map(s => `[${s.id === editedSectionId ? 'EDITED' : 'OK'}] §${s.id} ${s.title}\n${s.content}`).join('\n\n---\n\n')}

Return ONLY valid JSON with this exact schema:
{
  "conflicts": [
    {
      "section_id": "id of the section that conflicts with the edit",
      "type": "contradiction | redundancy | orphan",
      "description": "one sentence on what the conflict is"
    }
  ]
}

Definitions:
- contradiction: the edited section now says X, another section still says not-X.
- redundancy: the edited section now overlaps significantly with another section.
- orphan: the edited section removed or changed something another section still references.

Rules:
- Only flag REAL conflicts. Do not flag stylistic differences or minor overlap.
- Empty conflicts array if there are none. Do not invent issues.
- Be specific in descriptions: name what conflicts and how.`;

const PROMPT_LLM_JUDGE = ({ criterion, output, projectContext }) => `You are evaluating whether a model's output meets a specified criterion. Be strict but fair.

${projectContext ? `PROJECT CONTEXT (for understanding what the criterion means in context):\n${JSON.stringify(projectContext, null, 2)}\n` : ''}
CRITERION:
${criterion}

OUTPUT TO EVALUATE:
"""
${output}
"""

Return ONLY valid JSON with this exact schema:
{
  "passed": true | false,
  "reasoning": "one or two sentences on why it passed or failed"
}

Rules:
- "passed" is a boolean, not a string.
- Judge against the criterion only. Do not introduce additional standards.
- If the criterion is ambiguous, lean toward "passed: false" with reasoning that names the ambiguity.`;

// ---------------------------------------------------------------------
// 3. CORE OPERATIONS
// ---------------------------------------------------------------------
// Each of these is a pure async function. They take inputs, call Claude,
// return structured results. No React state, no UI. Easy to lift out.
// ---------------------------------------------------------------------

async function detectSections(rawInput, mode) {
  const result = await callClaudeJSON({
    system: PROMPT_SECTION_DETECTOR(mode),
    userMessage: rawInput,
    maxTokens: 4000,
  });
  // Add stable ids client-side
  return result.sections.map((s, i) => ({
    id: `s${i + 1}`,
    title: s.title,
    kind: s.kind,
    content: s.content,
    rationale: s.rationale,
    history: [],
  }));
}

async function extractContext(rawText) {
  const extracted = await callClaudeJSON({
    system: PROMPT_CONTEXT_EXTRACTOR,
    userMessage: rawText,
    maxTokens: 1500,
  });
  return { raw: rawText, extracted };
}

async function iterateSection({ mode, section, fullDocument, projectContext, chatHistory, userMessage }) {
  const result = await callClaudeJSON({
    system: PROMPT_ITERATION({
      mode,
      projectContext: projectContext?.extracted,
      fullDocument,
      currentSection: section,
      chatHistory,
      userMessage,
    }),
    userMessage: userMessage,
    maxTokens: 3000,
  });
  return {
    rewrittenContent: result.rewritten_content,
    reasoning: result.reasoning,
    clarifyingQuestion: result.clarifying_question || null,
    suggestedContextUpdate: result.suggested_context_update || null,
  };
}

async function detectConflicts({ sections, editedSectionId, projectContext }) {
  const result = await callClaudeJSON({
    system: PROMPT_CONFLICT_DETECTOR({
      sections,
      editedSectionId,
      projectContext: projectContext?.extracted,
    }),
    userMessage: "Check for conflicts now.",
    maxTokens: 1500,
  });
  return result.conflicts || [];
}

// ---------------------------------------------------------------------
// 4. TEST RUNNER (prompt mode)
// ---------------------------------------------------------------------
// renderTemplate substitutes {{var}} placeholders. evaluateAssertion runs
// one assertion (substring is local, semantic uses LLM judge, structural
// uses local JSON schema check). runTest orchestrates: render prompt,
// call Claude, run all assertions, aggregate.
// ---------------------------------------------------------------------

function renderTemplate(template, vars) {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => {
    if (key in vars) return vars[key];
    return `{{${key}}}`; // leave unresolved if missing
  });
}

async function evaluateAssertion({ assertion, output, projectContext }) {
  switch (assertion.type) {
    case 'substring': {
      // spec: { mode: 'must_include' | 'must_not_include', text: string }
      const has = output.includes(assertion.spec.text);
      const passed = assertion.spec.mode === 'must_include' ? has : !has;
      return {
        passed,
        reasoning: passed
          ? `Output ${assertion.spec.mode === 'must_include' ? 'contains' : 'does not contain'} "${assertion.spec.text}"`
          : `Output ${assertion.spec.mode === 'must_include' ? 'is missing' : 'unexpectedly contains'} "${assertion.spec.text}"`,
      };
    }
    case 'structural': {
      // spec: { schema: 'json' | 'json_with_keys', keys?: string[] }
      try {
        const cleaned = output.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
        const parsed = JSON.parse(cleaned);
        if (assertion.spec.schema === 'json_with_keys') {
          const missing = (assertion.spec.keys || []).filter(k => !(k in parsed));
          if (missing.length > 0) {
            return { passed: false, reasoning: `JSON missing keys: ${missing.join(', ')}` };
          }
        }
        return { passed: true, reasoning: 'Output is valid JSON with required keys' };
      } catch {
        return { passed: false, reasoning: 'Output is not valid JSON' };
      }
    }
    case 'semantic': {
      // spec: { criterion: string }
      const judgment = await callClaudeJSON({
        system: PROMPT_LLM_JUDGE({
          criterion: assertion.spec.criterion,
          output,
          projectContext: projectContext?.extracted,
        }),
        userMessage: "Judge now.",
        maxTokens: 500,
      });
      return { passed: judgment.passed, reasoning: judgment.reasoning };
    }
    case 'reference': {
      // spec: { reference: string, similarity_threshold: number }
      // Simple word-overlap similarity for V1. Replace with embedding similarity later.
      const tokenize = s => s.toLowerCase().match(/\w+/g) || [];
      const a = new Set(tokenize(output));
      const b = new Set(tokenize(assertion.spec.reference));
      const intersection = [...a].filter(x => b.has(x)).length;
      const union = new Set([...a, ...b]).size;
      const sim = union === 0 ? 0 : intersection / union;
      const threshold = assertion.spec.similarity_threshold ?? 0.5;
      return {
        passed: sim >= threshold,
        reasoning: `Jaccard similarity ${sim.toFixed(2)} vs threshold ${threshold}`,
      };
    }
    default:
      return { passed: false, reasoning: `Unknown assertion type: ${assertion.type}` };
  }
}

async function runTest({ promptDocument, testCase, projectContext }) {
  // Concatenate sections to form the full prompt, then substitute vars
  const fullPrompt = promptDocument.sections.map(s => s.content).join('\n\n');
  const renderedPrompt = renderTemplate(fullPrompt, testCase.inputVars);

  const startTime = Date.now();
  let output;
  try {
    output = await callClaude({
      system: renderedPrompt,
      userMessage: testCase.context || "(no user message provided)",
      maxTokens: 2000,
    });
  } catch (e) {
    return {
      testCaseId: testCase.id,
      output: null,
      error: e.message,
      assertions: [],
      latencyMs: Date.now() - startTime,
      passed: false,
    };
  }
  const latencyMs = Date.now() - startTime;

  const assertionResults = [];
  for (const assertion of testCase.assertions) {
    const r = await evaluateAssertion({ assertion, output, projectContext });
    assertionResults.push({ ...r, assertion });
  }

  return {
    testCaseId: testCase.id,
    output,
    error: null,
    assertions: assertionResults,
    latencyMs,
    passed: assertionResults.every(r => r.passed),
  };
}

// ---------------------------------------------------------------------
// 5. DIFF
// ---------------------------------------------------------------------
// Line-level diff using LCS. Returns array of { type, text } where type
// is 'equal' | 'add' | 'remove'. Used by the diff view to highlight what
// changed between two versions of a section.
// ---------------------------------------------------------------------

function diffLines(oldText, newText) {
  const oldLines = (oldText || '').split('\n');
  const newLines = (newText || '').split('\n');
  const m = oldLines.length;
  const n = newLines.length;

  // Build LCS table
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (oldLines[i - 1] === newLines[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  // Walk back
  const result = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      result.unshift({ type: 'equal', text: oldLines[i - 1] });
      i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      result.unshift({ type: 'add', text: newLines[j - 1] });
      j--;
    } else {
      result.unshift({ type: 'remove', text: oldLines[i - 1] });
      i--;
    }
  }
  return result;
}

// ---------------------------------------------------------------------
// 6. VERSIONING
// ---------------------------------------------------------------------
// snapshotDocument creates an immutable copy of the current state for
// version history. rollbackToVersion replaces current state with a past
// snapshot. Versions also store test results so you can scrub through
// "what did the suite look like at v7".
// ---------------------------------------------------------------------

function snapshotDocument(document, testResults, conflicts) {
  return {
    timestamp: Date.now(),
    document: JSON.parse(JSON.stringify(document)), // deep clone
    testResults: testResults ? JSON.parse(JSON.stringify(testResults)) : null,
    conflicts: conflicts ? JSON.parse(JSON.stringify(conflicts)) : null,
  };
}

// =====================================================================
// 7. SCAFFOLDING UI (minimal — replace with real UI)
// =====================================================================
// What follows is a rough functional UI just to exercise the backend.
// Three panes, plain styling. Use this to verify the logic above works,
// then build the production interface separately. Anything fancy lives
// in your real UI, not here.
// =====================================================================

const ui = {
  page: { fontFamily: 'ui-sans-serif, system-ui, sans-serif', background: '#0f1011', color: '#e6e4e0', minHeight: '100vh' },
  bar: { display: 'flex', gap: 12, alignItems: 'center', padding: '10px 14px', borderBottom: '1px solid #2a2a2c', fontSize: 13 },
  btn: { background: '#1c1d1f', color: '#e6e4e0', border: '1px solid #333', padding: '4px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 12 },
  btnActive: { background: '#c9a66b', color: '#0f1011', border: '1px solid #c9a66b' },
  pane: { padding: 12, overflow: 'auto', borderRight: '1px solid #2a2a2c', fontSize: 13 },
  textarea: { width: '100%', background: '#1c1d1f', color: '#e6e4e0', border: '1px solid #333', borderRadius: 4, padding: 8, fontFamily: 'ui-monospace, monospace', fontSize: 12, resize: 'vertical' },
  section: { padding: 8, borderRadius: 4, cursor: 'pointer', marginBottom: 4, border: '1px solid transparent' },
  sectionActive: { background: '#1c1d1f', border: '1px solid #c9a66b' },
  kindTag: { fontSize: 10, color: '#9a9690', textTransform: 'uppercase', letterSpacing: 0.5 },
  rationale: { fontSize: 12, color: '#9a9690', fontStyle: 'italic', marginBottom: 8 },
  chatBox: { background: '#0a0b0c', border: '1px solid #333', borderRadius: 4, padding: 8, marginTop: 8, fontSize: 12 },
  diffEqual: { color: '#9a9690' },
  diffAdd: { background: '#1a2e1d', color: '#88a982' },
  diffRemove: { background: '#2e1a1d', color: '#c97b6b' },
  pass: { color: '#88a982' },
  fail: { color: '#c97b6b' },
  conflict: { padding: 8, marginBottom: 6, border: '1px solid #c97b6b', borderRadius: 4, background: '#2e1a1d', fontSize: 12 },
};

export default function App() {
  // Top-level state
  const [mode, setMode] = useState('prompt'); // 'prompt' | 'plan'
  const [rawInput, setRawInput] = useState('');
  const [contextRaw, setContextRaw] = useState('');
  const [projectContext, setProjectContext] = useState(null);
  const [document, setDocument] = useState(null); // { sections, testCases }
  const [selectedSectionId, setSelectedSectionId] = useState(null);
  const [chatBySection, setChatBySection] = useState({}); // { sectionId: [{role, text}] }
  const [chatInput, setChatInput] = useState('');
  const [conflicts, setConflicts] = useState([]);
  const [testResults, setTestResults] = useState({}); // { testCaseId: result }
  const [versions, setVersions] = useState([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [previousSection, setPreviousSection] = useState(null); // for diff view

  const selectedSection = useMemo(
    () => document?.sections.find(s => s.id === selectedSectionId) || null,
    [document, selectedSectionId]
  );

  // ---- Operations ----

  const wrap = useCallback(async (label, fn) => {
    setBusy(label);
    setError('');
    try {
      return await fn();
    } catch (e) {
      setError(e.message);
      console.error(e);
    } finally {
      setBusy('');
    }
  }, []);

  const handleAnalyzeInput = () => wrap('Detecting sections...', async () => {
    if (!rawInput.trim()) return;
    const sections = await detectSections(rawInput, mode);
    setDocument({ sections, testCases: [] });
    setSelectedSectionId(sections[0]?.id || null);
    setVersions([]);
    setConflicts([]);
    setTestResults({});
    setChatBySection({});
  });

  const handleExtractContext = () => wrap('Extracting context...', async () => {
    if (!contextRaw.trim()) return;
    const ctx = await extractContext(contextRaw);
    setProjectContext(ctx);
  });

  const handleSendMessage = () => wrap('Iterating...', async () => {
    if (!chatInput.trim() || !selectedSection || !document) return;

    const history = chatBySection[selectedSection.id] || [];
    const userMsg = { role: 'user', text: chatInput };
    const newHistory = [...history, userMsg];
    setChatBySection(prev => ({ ...prev, [selectedSection.id]: newHistory }));
    setChatInput('');

    const fullDoc = document.sections.map(s => `[§${s.id} ${s.title}]\n${s.content}`).join('\n\n');

    const result = await iterateSection({
      mode,
      section: selectedSection,
      fullDocument: fullDoc,
      projectContext,
      chatHistory: history,
      userMessage: userMsg.text,
    });

    // Append assistant message to chat
    setChatBySection(prev => ({
      ...prev,
      [selectedSection.id]: [
        ...newHistory,
        {
          role: 'assistant',
          text: result.reasoning + (result.clarifyingQuestion ? `\n\nQ: ${result.clarifyingQuestion}` : ''),
          suggestedContextUpdate: result.suggestedContextUpdate,
        },
      ],
    }));

    // If content changed, save the previous and update the section
    if (result.rewrittenContent !== selectedSection.content && !result.clarifyingQuestion) {
      setPreviousSection({ ...selectedSection });
      const updatedSection = {
        ...selectedSection,
        content: result.rewrittenContent,
        history: [
          ...selectedSection.history,
          {
            timestamp: Date.now(),
            userMessage: userMsg.text,
            oldContent: selectedSection.content,
            newContent: result.rewrittenContent,
            reasoning: result.reasoning,
          },
        ],
      };
      const updatedDoc = {
        ...document,
        sections: document.sections.map(s => s.id === selectedSection.id ? updatedSection : s),
      };
      setDocument(updatedDoc);

      // Plan mode: run conflict detection
      if (mode === 'plan') {
        const newConflicts = await detectConflicts({
          sections: updatedDoc.sections,
          editedSectionId: selectedSection.id,
          projectContext,
        });
        setConflicts(newConflicts);
      }

      // Snapshot version
      setVersions(prev => [...prev, snapshotDocument(updatedDoc, testResults, conflicts)]);
    }
  });

  const handleAcceptContextUpdate = (update) => {
    if (!projectContext) return;
    setContextRaw(prev => prev + (prev ? '\n' : '') + update);
    // Re-extract on next manual click; or do it now:
    wrap('Updating context...', async () => {
      const ctx = await extractContext(contextRaw + '\n' + update);
      setProjectContext(ctx);
    });
  };

  const handleRunTests = () => wrap('Running tests...', async () => {
    if (!document || mode !== 'prompt') return;
    const results = {};
    for (const tc of document.testCases) {
      results[tc.id] = await runTest({ promptDocument: document, testCase: tc, projectContext });
    }
    setTestResults(results);
  });

  const handleAddSampleTest = () => {
    if (!document) return;
    const id = `t${document.testCases.length + 1}`;
    const newTest = {
      id,
      name: `Test ${id}`,
      inputVars: {},
      context: 'Sample user input — edit me',
      assertions: [
        { type: 'substring', spec: { mode: 'must_include', text: 'example' } },
        { type: 'semantic', spec: { criterion: 'Output is helpful and direct' } },
      ],
      tags: ['happy_path'],
    };
    setDocument({ ...document, testCases: [...document.testCases, newTest] });
  };

  const handleRollback = (version) => {
    setDocument(version.document);
    setTestResults(version.testResults || {});
    setConflicts(version.conflicts || []);
    setSelectedSectionId(version.document.sections[0]?.id || null);
  };

  const handleExport = () => {
    if (!document) return;
    const content = document.sections.map(s => s.content).join('\n\n');
    navigator.clipboard?.writeText(content);
    alert('Copied current document to clipboard');
  };

  // ---- Render ----

  if (!document) {
    return (
      <div style={ui.page}>
        <div style={ui.bar}>
          <strong>Optimizer</strong>
          <button
            style={mode === 'prompt' ? { ...ui.btn, ...ui.btnActive } : ui.btn}
            onClick={() => setMode('prompt')}
          >Prompt mode</button>
          <button
            style={mode === 'plan' ? { ...ui.btn, ...ui.btnActive } : ui.btn}
            onClick={() => setMode('plan')}
          >Plan mode</button>
          <span style={{ marginLeft: 'auto', color: '#9a9690', fontSize: 12 }}>{busy || ' '}</span>
        </div>
        <div style={{ padding: 24, maxWidth: 800, margin: '0 auto' }}>
          <h2 style={{ fontWeight: 400, marginBottom: 12 }}>Project context</h2>
          <p style={{ color: '#9a9690', fontSize: 13, marginBottom: 8 }}>
            Dump anything — bullets, ramblings, half a tech spec. An LLM will structure it.
          </p>
          <textarea
            style={{ ...ui.textarea, minHeight: 100 }}
            value={contextRaw}
            onChange={e => setContextRaw(e.target.value)}
            placeholder="What you're building, tech stack, constraints, decisions made..."
          />
          <button style={{ ...ui.btn, marginTop: 8 }} onClick={handleExtractContext} disabled={!!busy}>
            Extract context
          </button>
          {projectContext && (
            <pre style={{ background: '#1c1d1f', padding: 8, borderRadius: 4, marginTop: 8, fontSize: 11, color: '#9a9690', whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(projectContext.extracted, null, 2)}
            </pre>
          )}

          <h2 style={{ fontWeight: 400, marginBottom: 12, marginTop: 24 }}>
            Paste your {mode === 'prompt' ? 'prompt' : 'markdown plan'}
          </h2>
          <textarea
            style={{ ...ui.textarea, minHeight: 240 }}
            value={rawInput}
            onChange={e => setRawInput(e.target.value)}
            placeholder={mode === 'prompt'
              ? "Paste a full prompt. Sections will be auto-detected."
              : "Paste a markdown plan. Sections will be auto-detected."}
          />
          <button style={{ ...ui.btn, marginTop: 8 }} onClick={handleAnalyzeInput} disabled={!!busy || !rawInput.trim()}>
            Analyze and split into sections
          </button>
          {error && <div style={{ color: '#c97b6b', marginTop: 8, fontSize: 12 }}>{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div style={ui.page}>
      <div style={ui.bar}>
        <strong>Optimizer</strong>
        <button
          style={mode === 'prompt' ? { ...ui.btn, ...ui.btnActive } : ui.btn}
          onClick={() => setMode('prompt')}
        >Prompt</button>
        <button
          style={mode === 'plan' ? { ...ui.btn, ...ui.btnActive } : ui.btn}
          onClick={() => setMode('plan')}
        >Plan</button>
        <span style={{ color: '#9a9690' }}>·</span>
        <button style={ui.btn} onClick={() => setDocument(null)}>New document</button>
        <button style={ui.btn} onClick={handleExport}>Export</button>
        {mode === 'prompt' && (
          <>
            <button style={ui.btn} onClick={handleAddSampleTest}>+ test</button>
            <button style={ui.btn} onClick={handleRunTests} disabled={!!busy || document.testCases.length === 0}>
              Run tests
            </button>
          </>
        )}
        <span style={{ marginLeft: 'auto', color: '#9a9690', fontSize: 12 }}>
          {busy || `v${versions.length} · ${document.sections.length} sections`}
        </span>
      </div>

      {error && <div style={{ padding: 8, background: '#2e1a1d', color: '#c97b6b', fontSize: 12 }}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 1fr', height: 'calc(100vh - 42px)' }}>
        {/* LEFT: section list */}
        <div style={ui.pane}>
          <div style={{ marginBottom: 8, color: '#9a9690', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Sections
          </div>
          {document.sections.map(s => (
            <div
              key={s.id}
              style={s.id === selectedSectionId ? { ...ui.section, ...ui.sectionActive } : ui.section}
              onClick={() => setSelectedSectionId(s.id)}
            >
              <div style={ui.kindTag}>§{s.id} · {s.kind}</div>
              <div>{s.title}</div>
              {s.history.length > 0 && (
                <div style={{ fontSize: 10, color: '#c9a66b', marginTop: 2 }}>
                  {s.history.length} edit{s.history.length === 1 ? '' : 's'}
                </div>
              )}
            </div>
          ))}

          <div style={{ marginTop: 16, color: '#9a9690', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Versions
          </div>
          {versions.length === 0 && <div style={{ fontSize: 11, color: '#666' }}>(none yet)</div>}
          {versions.map((v, i) => (
            <div
              key={i}
              style={{ ...ui.section, fontSize: 11 }}
              onClick={() => handleRollback(v)}
            >
              v{i + 1} · {new Date(v.timestamp).toLocaleTimeString()}
            </div>
          ))}
        </div>

        {/* MIDDLE: section + chat */}
        <div style={ui.pane}>
          {selectedSection && (
            <>
              <div style={ui.kindTag}>§{selectedSection.id} · {selectedSection.kind}</div>
              <h3 style={{ fontWeight: 400, margin: '4px 0 8px 0' }}>{selectedSection.title}</h3>
              <div style={ui.rationale}>{selectedSection.rationale}</div>
              <pre style={{
                background: '#1c1d1f', padding: 10, borderRadius: 4, fontSize: 12,
                whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, monospace', maxHeight: '40vh', overflow: 'auto'
              }}>
                {selectedSection.content}
              </pre>

              <div style={{ marginTop: 12, color: '#9a9690', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Chat (scoped to this section)
              </div>
              <div style={{ maxHeight: '20vh', overflow: 'auto', marginTop: 4 }}>
                {(chatBySection[selectedSection.id] || []).map((m, i) => (
                  <div key={i} style={ui.chatBox}>
                    <div style={{ fontSize: 10, color: '#9a9690', marginBottom: 4 }}>{m.role}</div>
                    <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
                    {m.suggestedContextUpdate && (
                      <button
                        style={{ ...ui.btn, marginTop: 6, fontSize: 11 }}
                        onClick={() => handleAcceptContextUpdate(m.suggestedContextUpdate)}
                      >
                        + add to context: {m.suggestedContextUpdate}
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <textarea
                style={{ ...ui.textarea, minHeight: 60, marginTop: 8 }}
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                placeholder="Ask why this section is the way it is, or request a change..."
                onKeyDown={e => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSendMessage();
                }}
              />
              <button style={{ ...ui.btn, marginTop: 4 }} onClick={handleSendMessage} disabled={!!busy}>
                Send (⌘+Enter)
              </button>
            </>
          )}
        </div>

        {/* RIGHT: diff + tests/conflicts */}
        <div style={{ ...ui.pane, borderRight: 'none' }}>
          <div style={{ color: '#9a9690', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
            Diff (last edit on selected section)
          </div>
          {selectedSection && selectedSection.history.length > 0 ? (
            <pre style={{ fontSize: 11, fontFamily: 'ui-monospace, monospace', background: '#0a0b0c', padding: 8, borderRadius: 4, maxHeight: '30vh', overflow: 'auto' }}>
              {diffLines(
                selectedSection.history[selectedSection.history.length - 1].oldContent,
                selectedSection.history[selectedSection.history.length - 1].newContent
              ).map((d, i) => (
                <div key={i} style={
                  d.type === 'equal' ? ui.diffEqual :
                  d.type === 'add' ? ui.diffAdd : ui.diffRemove
                }>
                  {d.type === 'equal' ? '  ' : d.type === 'add' ? '+ ' : '- '}{d.text}
                </div>
              ))}
            </pre>
          ) : (
            <div style={{ color: '#666', fontSize: 12 }}>(no edits yet on this section)</div>
          )}

          {mode === 'prompt' && (
            <>
              <div style={{ color: '#9a9690', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 16, marginBottom: 8 }}>
                Tests ({document.testCases.length})
              </div>
              {document.testCases.length === 0 && (
                <div style={{ fontSize: 12, color: '#666' }}>
                  No tests yet. Click "+ test" in the top bar to add a sample. Edit it in code (or build a UI for it later).
                </div>
              )}
              {document.testCases.map(tc => {
                const r = testResults[tc.id];
                return (
                  <div key={tc.id} style={{ ...ui.chatBox, marginTop: 4 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <strong>{tc.name}</strong>
                      {r && <span style={r.passed ? ui.pass : ui.fail}>
                        {r.passed ? '✓ pass' : '✗ fail'} · {r.latencyMs}ms
                      </span>}
                    </div>
                    {r?.assertions.map((a, i) => (
                      <div key={i} style={{ fontSize: 11, marginTop: 4 }}>
                        <span style={a.passed ? ui.pass : ui.fail}>{a.passed ? '✓' : '✗'}</span>{' '}
                        <span style={{ color: '#9a9690' }}>{a.assertion.type}</span>{' '}
                        — {a.reasoning}
                      </div>
                    ))}
                    {r?.error && <div style={ui.fail}>Error: {r.error}</div>}
                  </div>
                );
              })}
            </>
          )}

          {mode === 'plan' && (
            <>
              <div style={{ color: '#9a9690', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 16, marginBottom: 8 }}>
                Conflicts ({conflicts.length})
              </div>
              {conflicts.length === 0 && <div style={{ fontSize: 12, color: '#666' }}>(no conflicts detected)</div>}
              {conflicts.map((c, i) => (
                <div key={i} style={ui.conflict} onClick={() => setSelectedSectionId(c.section_id)}>
                  <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, color: '#c97b6b' }}>
                    {c.type} · §{c.section_id}
                  </div>
                  <div style={{ marginTop: 2 }}>{c.description}</div>
                </div>
              ))}
            </>
          )}

          {projectContext && (
            <>
              <div style={{ color: '#9a9690', fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 16, marginBottom: 4 }}>
                Project context
              </div>
              <pre style={{ fontSize: 10, color: '#9a9690', whiteSpace: 'pre-wrap', maxHeight: '20vh', overflow: 'auto' }}>
                {JSON.stringify(projectContext.extracted, null, 2)}
              </pre>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
