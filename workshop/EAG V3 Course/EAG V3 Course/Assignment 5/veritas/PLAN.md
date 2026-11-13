# Veritas → Essay Writer: Roadmap

Living plan. Add comments/checkboxes/new items directly in this file as
things come up — nothing here is final until you say so.

**Status: Phases 1–3 built.** `compose`, the topic pipeline
(`scope`/`compose_topic`), and the Streamlit UI (`app.py`) all exist and
are wired up. A project-local venv was created at `veritas/.venv`
(`pip install -r requirements.txt` there) since the system Python had no
usable pip. Not yet run end-to-end against a live API key in this
environment — no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` was available here,
so the pipeline itself, the Streamlit boot, and the HTML rendering were
each verified separately but not one live claim/topic run through the UI.
Worth doing that once you have a key in hand.

**Decisions locked in so far:**
- Claim-verification pipeline stays exactly as it is today (decompose →
  search → fetch → extract → grade → synthesize → verify). We fold essay
  writing into it as a new final step, verdict included *inside* the essay
  rather than as a separate bolted-on block.
- Topic exploration ("look into X for me") is a **separate, new pipeline**
  alongside claim verification, not a mode-flag inside the existing one.
- UI is **Streamlit** — pure Python, fastest to stand up and extend, good
  fit for showing live pipeline progress next to a long-form essay.

---

## Phase 1 — Essay-writing step for the existing claim pipeline

Goal: `python cli.py "<claim>"` still verifies a claim, but the final
output is a readable explanatory essay with the verdict woven in, not a
verdict block with rationale bullets.

- [x] Add `compose` as an 8th skill in `config.yaml` (`depends_on: [verify]`)
- [x] Write `prompts/compose.md` — contract for turning
      `{claim, decomposition, synthesis, findings, grades, audit}` into a
      long-form essay (target ~600–1000 words): explain the science first,
      state the verdict and *why* inline with citations, note open gaps,
      end plainly. No new facts — every empirical sentence still needs a
      `source_id`, same discipline as the rest of the pipeline.
- [x] Update `PROMPT.md` master prompt: list `compose` as skill 8, add its
      OUTPUT_SCHEMA note, and a TONE addendum — "teaching essay for a
      curious non-specialist," distinct from the clinical tone of
      `synthesize`.
- [x] `orchestrator.py`: call `compose` once `verify` approves (or hits
      `MAX_ROUNDS`), store `result["essay"]` (also added `result["sources"]`
      — full bibliographic metadata wasn't being persisted anywhere before,
      the UI needs it for clickable citations)
- [x] `cli.py`: print the essay (wrapped) instead of / above the current
      verdict block; verdict/audit still printed underneath as `DETAIL`
- [ ] Re-run both existing saved claims (`runs/*.json` shows the two prior
      test claims) against a live API key to sanity check the new step —
      **not done in this environment, no API key was available.** Do this
      first before trusting the essay output.

## Phase 2 — New topic-exploration pipeline

Goal: `python cli.py --topic "<topic>"` (or a separate entry point) takes
an open subject, researches it the same way, and produces an essay with
no verdict — this is exploration, not adjudication.

- [x] New skills added to the same `skills:` map in `config.yaml` (a
      separate `topic_skills:` block turned out to be unnecessary — `scope`
      and `compose_topic` just needed entries beside the existing ones,
      since `_invoke` looks skills up from one flat `cfg["skills"]` dict):
      `scope → search → fetch → extract → grade → compose_topic`
- [x] `prompts/scope.md` — replaces `decompose`: turns a topic into a small
      set of key questions/angles worth covering (instead of falsifiable
      sub-claims). No "falsifier" field, no verdict framing.
- [x] Reuse `search`, `fetch` (sources.py, unchanged), `extract`, `grade`
      as-is — confirmed during implementation: they only need `id`/`text`
      shaped items, so topic `questions` are passed in under the same
      `sub_claims` key the claim pipeline uses and everything reads fine
- [x] `prompts/compose_topic.md` — essay contract for topic mode: survey
      the questions, cite findings on each, be explicit about open
      questions/disagreement in the literature, no forced verdict
- [x] Decided: **no verify-equivalent audit step for topic mode.** Single
      pass (`scope` runs once, no re-search loop) — grade + the same
      citation discipline as the claim pipeline is enough for an
      exploratory essay that isn't adjudicating anything. Documented in
      `PROMPT.md`'s CONVERSATION AND STATE section. Revisit if essays turn
      out thin on hard topics — multi-round topic search is a plausible
      backlog item.
- [x] New orchestrator entry point: `TopicExplorer` class in
      `orchestrator.py`, composing a `Veritas` instance internally to reuse
      `_invoke`/`_extract_parallel`/`_finish` rather than duplicating the
      retry/parsing/trace-saving plumbing — `Veritas.run(claim)` untouched
- [x] `cli.py`: `--topic`/`-t` flag, own report renderer (`report_topic`)

## Phase 3 — Streamlit UI

Goal: one local app, both modes, live progress, readable essay output.

- [x] `app.py` (Streamlit): text input + mode toggle (Verify a claim /
      Explore a topic), Run button. Sidebar also takes a session-only API
      key paste if `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` isn't set in the
      environment, so it's usable without touching a shell.
- [x] Live progress: `Trace` now takes an `on_log` callback (`orchestrator.py`)
      threaded from `Veritas`/`TopicExplorer` through to an `st.status()`
      block in `app.py`, so the UI shows the same step-by-step log the CLI
      prints (`[1/8] decompose`, …) instead of a silent spinner.
- [x] Result view: essay rendered in a styled "paper" card (Fraunces
      headings, Source Serif 4 body, inline `(source_id)` citation
      highlighting), with a verdict badge + audit summary (claim mode) or
      open-questions list (topic mode), a sources panel with real
      title/author/venue/links, and a raw-trace JSON expander for
      debugging.
- [x] Run history: sidebar lists past runs from `runs/*.json`, clicking one
      loads it into the main view without re-running the pipeline.
- [x] Used the `frontend-cc` skill (Streamlit reference) for the visual
      pass: Fraunces/Source Serif 4/DM Sans pairing, dark ink chrome around
      a warm cream "paper" reading surface, amber accent — not the default
      Streamlit look.

## Backlog — future additions (unscoped, add freely)

- [x] Export essay to a standalone Markdown file — `st.download_button` in
      `app.py` (PDF still open, markdown was the cheap win)
- [ ] Follow-up Q&A on a generated essay (chat with the sources already
      gathered, no new fetch round)
- [ ] Citation formatting options (inline source_id vs numbered vs APA)
- [ ] Compare two topics/claims side by side
- [ ] Reuse/cache sources across runs on similar topics to cut API calls
- [x] Cost/token display live in the UI — shown in the metadata row under
      the essay
- [ ] Multi-round topic search (see Phase 2's audit-step decision above)
- [ ] PDF export
- [ ] A real end-to-end run through the UI with a live API key — nothing
      in this environment had one; see Phase 1's unchecked item

---

## Phase 4 — Hardening (done)

- [x] `citations.py` — deterministic citation integrity. Scans **all** prose,
      not just `source_id` fields, because the defect run 2 exposed was in
      `verdict_rationale`. Injected as check `C0` into `audit["checks"]` so the
      CLI and UI render it with no changes, and it **overrides** an `approved`
      audit, forcing a retry round. Topic mode gets the same check on its essay
      under `result["citation_check"]`.
- [x] `tests/` — offline, no API key, no network. `test_citations.py` replays
      the run-2 trace as a regression fixture; `test_pipeline_gate.py` drives
      the whole claim pipeline with a stubbed LLM and proves the gate forces a
      second round (which also exercises the `needs_more_evidence` splice that
      no committed run had reached).
- [x] Split the system prompt into two cached blocks (master + contract). The
      master prompt is byte-identical across all ten skills, so it is now a
      cache read on every call after the first instead of each skill writing
      its own copy. `tokens.cache_read` in the trace is how you check it worked.
- [x] `max_tokens` 8000 → 16000. Thinking and response share that budget, and
      `compose` targets a 600–1000 word essay.

## Your notes
<!-- add comments, priorities, or new items below -->
