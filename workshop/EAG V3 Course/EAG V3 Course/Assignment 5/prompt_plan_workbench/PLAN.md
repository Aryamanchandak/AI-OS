# Prompt Constructor: Roadmap

Living plan. Add comments/checkboxes/new items directly in this file as
things come up — nothing here is final until you say so.

**Status: implemented.**

## Why

The workbench today only evaluates a prompt or plan you already wrote. But
the highest-stakes prompts are exactly the ones you're worst positioned to
write well yourself — e.g. a Veritas-style research prompt on a scientific
topic you personally have no expertise in. A vague or under-specified input
doesn't fail loudly; it just quietly steers an expensive multi-call pipeline
in a direction you can't sanity-check, and you only find out at the end.

The Constructor is a front door for that case, but scoped generally: given
any rough goal ("I want a prompt that does X"), it interviews you — one
question at a time, adaptive, follow-ups on your answers — until it has
enough context to draft a real prompt or plan. That draft then flows
straight into the existing evaluator, so construct → evaluate → refine is
one loop instead of three disconnected tools. This is general-purpose (any
prompt or plan), not Veritas-specific — Veritas is just the motivating case
that made the risk of under-specification obvious.

**Decisions locked in so far:**

- Lives **inside** `prompt_plan_workbench`, as a second page of the same
Streamlit app — not a new project, not inside `veritas/`. It shares
`engine.py`'s provider plumbing (`ModelSettings`, `_resolve_provider`,
`_extract_json`) and the "load the governing doc fresh from disk on every
call" pattern already established for `MAIN_PROMPT.md`.
- General-purpose, not Veritas-specific. No Veritas import, no assumption
the output is a claim/topic string. The output is the same `(kind, content, context)` shape the evaluator already accepts — `kind` is
`prompt` or `plan`, same as today.
- Conversational, not a static form. One question at a time; the model
decides what to ask next based on the history so far, not a fixed
checklist walked in order.
- Bounded, like Veritas's own `MAX_ROUNDS` pattern (`PROMPT.md`) — the
interview must terminate on its own after enough turns, or on user
request ("just draft what you have"), not run forever.
- Hands off into the *existing* evaluate flow rather than growing a third,
parallel output path — the whole point is one connected loop, not three
disconnected tools that happen to share a repo.

---



## Phase 1 — Conversational engine plumbing

Goal: `engine.py` can hold a multi-turn conversation, not just one
system+user call. `_resolve_provider`/`_extract_json` are reused unchanged;
only the completion call needs to speak "message list" instead of a single
turn.

- [x] Add `_complete_chat(system: str, messages: list[dict], settings) ->
  ```
  str` in `engine.py`. OpenAI branch: pass `messages` through as-is
  (already list-shaped) with the system prompt prepended. Anthropic
  branch: `system=system`, `messages=messages` (already close to what
  `_complete_json` does for a single turn — this generalizes it to N
  turns instead of duplicating the SDK-call logic).
  ```
  - Keep `_complete_json` for the existing single-shot evaluate/apply calls
  — don't refactor working code to share machinery it doesn't need.
- [x] Add `load_constructor_prompt(path=DEFAULT_CONSTRUCTOR_PATH)` mirroring
  ```
  `load_rubric()` exactly (same error handling, same "empty file
  raises" behavior). `DEFAULT_CONSTRUCTOR_PATH = ROOT.parent /
  "CONSTRUCTOR_PROMPT.md"`.
  ```
- [x] Add `converse(history: list[dict], settings, complete=_complete_chat)
  ```
  -> dict` — one call per turn. Builds `system =
  load_constructor_prompt()`, sends `history` (already includes the
  latest user message), parses the JSON reply via `_extract_json`,
  normalizes into:
  ```
  {"question": "<next question to ask, or empty if ready>",
   "notes": "<what's been learned so far, shown in the draft panel>",
   "ready": bool,
   "draft_kind": "prompt" | "plan" | null,
   "draft_content": "<full draft prompt/plan, only once ready>",
   "draft_context": "<usage context to prefill the evaluator with>"}
  ```
  Raise `WorkbenchError` on missing/invalid shape, same discipline as
  `_normalize_evaluation`. `draft_context` must be the *distilled*
  usage context (audience, constraints, out-of-bounds behavior) for the
  evaluator's `<context>` block — not a transcript dump; `notes` is the
  running scratchpad shown in the UI that the model should draw
  `draft_context` from once ready. Keeping these distinct is what
  stops the evaluator from either getting a wall of raw chat or losing
  the context the interview extracted.
  ```



## Phase 2 — `CONSTRUCTOR_PROMPT.md`

Goal: a new top-level governing doc, sibling to `MAIN_PROMPT.md`, loaded
fresh every turn so edits take effect immediately (same guarantee the
README already makes for the rubric).

- [x] Role: an interviewer, not a drafter — until it has enough to draft,
  ```
  every reply is exactly one question, never a list of questions.
  ```
- [x] Must ask, early, which of `prompt` / `plan` the user is building —
  ```
  this single fact is what the *evaluator* already branches its rubric
  interpretation on (`engine.py`'s `_evaluation_contract`), so getting
  it wrong wastes the whole downstream loop.
  ```
- [x] Question bank is adaptive, not fixed — but seed it conceptually from
  ```
  the failure modes a target LLM pipeline would otherwise hit silently
  or expensively: ambiguous scope (multiple readings of the same
  request), missing constraints (audience, tone, format, length,
  what's out of bounds), undefined success/failure behavior (what
  should happen on bad input, on uncertainty, on conflicting
  instructions), and unstated depth/rigor expectations. `PROMPT.md`'s
  own `ERROR HANDLING AND FALLBACKS` section (`ambiguous_claim`,
  `out_of_scope`, `insufficient_input`) is a good worked example of
  exactly this class of gap being caught *after* the fact — the
  Constructor's job is to catch the general form of it *before*.
  ```
- [x] Must track what's already been said (full history is always in the
  ```
  call) and never re-ask something already answered.
  ```
- [x] Must set `ready: true` and produce a draft once it has enough — target
  ```
  a small bounded number of turns (document a concrete default, e.g.
  "aim for readiness within 5–8 questions"), and must also respect an
  explicit user request to stop early and draft from whatever it has.
  ```
- [x] Draft output is a real prompt/plan in the same spirit as
  ```
  `MAIN_PROMPT.md`'s own criteria (explicit reasoning, structured
  output, fallbacks, etc. where applicable) — it doesn't need to *pass*
  the rubric, that's the evaluator's job next, but it shouldn't be
  naively thin either.
  ```
- [x] Same untrusted-input discipline as the rest of the workbench: user
  ```
  answers are data to extract context from, never instructions to the
  constructor itself.
  ```



## Phase 3 — Streamlit UI

Goal: a second page, chat-first, with a live draft panel and a one-click
handoff into the existing evaluate flow.

- [x] Add `pages/1_Constructor.py`; Streamlit auto-registers it as a second
  ```
  page with no changes to `app.py`. `app.py` stays the entry point
  exactly as documented (`streamlit run app.py`, `README.md`,
  `WORKFLOW.md`) — do not move or restructure it. Both pages share
  `st.session_state`, which is what makes the handoff in the next
  bullet possible without any file I/O.
  ```
- [x] Chat UI via `st.chat_message`/`st.chat_input`, backed by a
  ```
  `st.session_state.constructor_history` list, same
  `if key not in st.session_state` bootstrap idiom already used for
  `DEFAULTS` in `app.py`.
  ```
- [x] Live "Draft so far" side panel rendering `notes`/`draft_kind` as they
  ```
  accumulate turn to turn — visibility into what's been captured even
  before `ready`, not a black box until the end.
  ```
- [x] "Start over" control that clears `constructor_history` and any draft
  ```
  state — chat state persists across reruns like everything else in
  this app, so it needs an explicit reset.
  ```
- [x] Once `ready`: show the full draft, and a "Send to Evaluator →" button
  ```
  that writes `draft_kind`/`draft_content`/`draft_context` into the
  same session-state keys the evaluate page's text areas read, then
  `st.switch_page` back to it — the draft lands pre-filled, ready to
  evaluate immediately. This is the actual point of building it inside
  the same app instead of a separate tool. **Requires** giving the
  evaluate page's content/context `st.text_area`s explicit `key=`s and
  seeding them with `value=` from that same session-state (today
  they're read by return value only) — without this, the switch lands
  on an empty form and the whole handoff silently no-ops.
  ```



## Phase 4 — Tests

Goal: same offline discipline as `tests/test_engine.py` — no live model
call, no network.

- [x] `converse()` normalization tested with a stubbed `complete` callable
  ```
  (mirrors how `evaluate_content`/`apply_improvements` are tested
  today) — valid shape, missing-key shape, `ready=false` mid-interview
  shape.
  ```
- [x] `load_constructor_prompt()` missing/empty-file error paths, mirroring
  ```
  the existing `load_rubric()` tests.
  ```



## Explicitly out of scope for this plan

- No Veritas integration of any kind (no import, no auto-run, no "send
straight to the pipeline" button). The Constructor's only downstream
target is this app's own evaluator. If a direct Veritas handoff is
wanted later, it's a separate, later decision — not bundled in here.
- No cost/round estimator for the eventual downstream tool the draft might
be used with — that would require modeling a specific target pipeline,
which conflicts with staying general-purpose.



## Your notes

