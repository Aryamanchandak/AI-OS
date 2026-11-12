# Capstone scoping — adversarial code audit

Evidence base: direct file reads of `Personal/Research_MCP/` (citation_gate.py, trusted_sources.py,
triage.py, engine.py, ABSORPTION_SEAM_CHECKLIST.md), `Learning System/` (CLAUDE.md, study_core.py,
gateway.py, feynman_evaluator_v1.md, challenger_v1.md, config/baseline.json), `AI Agent/`
(README.md, agent7.py, decision.py, git log), `mcp_server/` (AGENTS.md, tools/ tree), and
`running.sh`. `pytest --collect-only` run against Learning System's real venv (39 tests collected,
matches CLAUDE.md claim). No paid API calls made.

## 1. Component table

| Component | Usable as-is | Needs real modification | Net-new | Estimate |
|---|---|---|---|---|
| **EAG V3 agent loop** (`AI Agent/`) | 5-stage loop, LLM gateway bridge, single stdio MCP client | Fix documented-but-unfixed regression (`index_document`/`search_knowledge` broken since 2026-07-05 — commit explicitly says "left unfixed"); add prompt framing that marks fetched/tool content as untrusted data (currently none — decision.py's SYSTEM prompt has no such instruction) | — | 2.5 days |
| **mcp_server research tools** (`mcp_server/tools/research/`) | Brave/arXiv/Semantic Scholar/Wikipedia/Google Books source fetchers already wired | — | New `research_verify`-style tool group wrapping Research_MCP's citation_gate/trusted_sources as a library, same adapter pattern already used for `study/` (lazy-init, thin MCP functions) | 3 days |
| **Research MCP core** (`Personal/Research_MCP/`) | `citation_gate.py` (deterministic, no LLM, genuinely solid), `trusted_sources.py` tiering, contracts/dedup | Has **no venv** — never provisioned in this checkout, not a git repo, last touched ~10 weeks ago. Must reconstruct env and smoke-test before trusting anything. Triage pins `model="claude-sonnet-4-6"` — verify this model id still resolves. citation_gate only checks citation *formatting/quote-matching* — it does not and cannot defend against a source claiming "already verified"; that's a different problem (see §2) | — | 1.5 days (env reconstruction + smoke test), folded into the row above |
| **Learning System grading** (`Learning System/`) | Prompt-render → gateway-call → persist plumbing (idempotency, structured JSON eval, `_validate_feynman_evaluation`) is real, tested, well-engineered | If reused via `StudyCore.evaluate_feynman`: requires a pre-seeded KG concept + vector-indexed "atomic facts." Production KG/vector adapters are unwired dev JSON fixtures (`kg_concepts_path`/`vector_snippets_path` both `null` in `config/baseline.json`, confirmed) — **not viable for arbitrary user-supplied topics in 4 weeks** | Both `feynman_evaluator_v1.md` and `challenger_v1.md` are Socratic-*question*-generators — neither ever outputs "this statement is factually wrong." No misconception/contradiction check exists anywhere in the prompt set. Recommended path (**A**): bypass `StudyCore`, write a new lightweight judge tool (verified brief + user explanation → verdict), reusing prompt *shape* and the idempotency/persist pattern only | 5 days (Path A) — see §2 for why this is a floor, not a target |
| **Learning System via StudyCore (Path B, not recommended)** | — | Build production `FinalKGRepository`/`VectorRepository` adapters, populate a KG per ad-hoc topic, honor the hard four-table schema constraint the repo's own CLAUDE.md enforces | Full KG population pipeline for arbitrary topics | +5–8 days on top of Path A, plus Neo4j/Ollama in prod (see deploy row) — do not attempt |
| **Deployment (EC2/Hetzner, real URL)** | Nothing. Zero Dockerfile/compose/systemd/nginx anywhere in the workspace. `running.sh` is a macOS-only local dev launcher (`open -a Ollama`) and itself admits "Neo4j not installed/configured yet" | — | Box provisioning, systemd units for llm_gateway + mcp_server + FastAPI app_planner, nginx + TLS, secrets management, smoke test | 2.5 days (Path A — no Neo4j/Ollama needed); +2 days if Path B |
| **Hostile-input test harness** | — | — | Two saved payloads (poisoned "already verified" doc; fluent-confidently-wrong explanation) + a repeatable script to fire them at the live URL and capture the judged response — this *is* the graded artifact, easy to leave until week 4 | 1 day |
| **Pitch prep** | — | — | 5-minute pitch | 1 day |

**Path A total: ~16.5 estimated days** against a ~20-working-day (4-week, 5 day/week) budget, before
any buffer for the fact that "5 days" on the grading prompt is an iteration estimate, not a
build estimate — see §2.

## 2. The highest-risk piece: misconception/confident-wrong grading

This is the piece the user already suspected, and the code confirms it's worse than "fiddly."

- Every grading prompt in the codebase (`feynman_evaluator_v1.md`, `challenger_v1.md`) is explicitly
  instructed to produce **questions, not verdicts** — "Do NOT give away answers — only ask
  questions." The one place `source_grounding_v1.md` uses "contradicts," it's checking whether a
  generated flashcard answer is grounded in cited text, not whether a student's free-text claim is
  false.
- Detecting "gaps" (missing facts) against a ground-truth list is a tractable retrieval-and-diff
  problem — the existing code already does this. Detecting "this sentence sounds right, uses the
  right vocabulary, and is wrong" is a different, harder problem: it requires the grader to
  actually model what the student said as a claim and check it against ground truth for
  *contradiction*, not just *coverage*. No code in this workspace does that today.
- `_validate_feynman_evaluation` is a cheap, permissive keys-presence check — adding a
  `misconceptions`/`contradictions` field to the schema is mechanical (one line). The cost is not
  plumbing. The cost is prompt-engineering iteration against real adversarial input until it
  reliably fires on subtly-wrong-but-fluent text without also flagging correct-but-unusually-phrased
  text (false positives will read, in a live pitch, exactly like the failure mode being graded on).
- Estimate: **5 days is a floor for a first working version**, and realistically eats a second
  chunk of week 3 or 4 if the first iteration doesn't hold up against hostile input B live. Budget
  this as the thing most likely to blow the schedule, not the deploy step.

## 3. Where "reuse is cheap" is true vs. wrong

**True:**
- mcp_server's existing source-fetching tools (Brave/arXiv/Semantic Scholar/Wikipedia/Google Books)
  are wired, tested-in-shape, and directly reusable for ask #1.
- `citation_gate.py` is genuinely solid, deterministic, no-LLM code — reuse it as-is for
  citation/quote-integrity checking.
- The adapter *pattern* (thin MCP tool functions wrapping a sibling package as a library, lazy
  singleton init, idempotency-key persistence) is proven twice already (`study/adapter.py` over
  `study_system`) and cheap to repeat for Research_MCP.

**Wrong, plainly:**
- "Research MCP citation-gate/provenance infra" is not currently *infrastructure* — it's an
  orphaned, un-provisioned prototype (no venv, not a git repo, not imported by anything live,
  last touched ~10 weeks before this audit). Reuse means reconstruct-then-integrate, not point-and-go.
- Reusing Learning System's grading "as-is" is not viable — its main entry point is contractually
  tied to a production knowledge graph that does not exist for arbitrary topics (confirmed null
  paths in the actual config file, not just a doc claim). What's reusable is the *prompt engineering
  pattern and persistence plumbing*, not the grading logic itself — and the grading logic is the
  one piece the assignment is actually testing.
- There is no deployment story to reuse at all — the workspace has never been run anywhere but a
  local Mac. "Deploy to EC2/Hetzner" is a from-scratch task with a real number of new pieces
  (process supervision, TLS, secrets, health checks under hostile-input load), not a config change.
- Net effect: Path A's ~16.5-day estimate consumes essentially the entire 4-week budget on its own.
  **There is no slack for scope expansion.** The premise that reuse buys room to do more should be
  inverted: reuse buys just enough room to do the scoped thing once, correctly, with a couple of
  days of buffer for the one piece (§2) that's genuinely uncertain.

## 4. Cut list — ranked, decide now, not under pressure

If behind at end of week 2, drop in this order. Each is chosen to protect the two things actually
graded (live app survives the two named hostile inputs; 5-minute pitch) while shedding the most
schedule risk per cut.

1. **Arbitrary-topic generality.** Pre-seed and pre-verify a small fixed set of 3–5 demo topics
   (with known-good and known-subtly-wrong example explanations already in hand) instead of a live
   judge that has to work on anything a person types. This directly removes the least-bounded,
   least-testable part of the misconception-grading problem while still fully satisfying the eval
   criteria — the two hostile inputs are tested against this curated set, live, on the deployed URL.
2. **Multi-turn Socratic challenger depth** (`follow_up_probes`, `edge_cases`, multi-round
   adversarial probing). Keep a single-shot verdict ("here's where you're wrong or hand-wavy") and
   drop the deepening Socratic loop. The existing challenger prompt already leans this direction
   (question-generation, not verdicts) — reusing it fully means building the multi-turn UX on top,
   which the eval criteria don't require.
3. **Ask #5 richness** ("what to re-check before trusting yourself at work"). The charter already
   punts this decision to the human — make the output a templated derivation from whatever gaps/
   misconceptions were already found in ask #3/#4, not a separate reasoning pass.
4. **Anything cosmetic** — UI polish, multi-agent orchestration flourishes, extra source types.
   Explicitly not graded per the user's own constraints; should already be near-zero investment,
   so there's little left to cut here, but it's the correct last resort before touching #1–#3.

## 5. Most likely way this quietly becomes a 4-month project

Not "misconception detection is fiddly" — that's real but bounded and already priced into §2.

The actual trap is architectural, and it's visible in the codebase's own habits: this workspace is
built by someone who, repeatedly, chooses to do things *properly* inside a constrained architecture
— a hard four-table schema rule the Learning System's own CLAUDE.md refuses to let you violate
without going back through a design doc, "one implementation of learning rules" with adapters that
must stay in sync across two separate git repos or "drift" (their word), an absorption-seam checklist
written for a prototype that was never absorbed, a documented-but-deliberately-unfixed regression
left in place rather than patched around. That discipline is a genuine asset in a non-deadline
project. Under a 4-week hard deadline it is the failure mode: the natural next step after "the
Feynman grader needs a real KG" is not "fake it for the demo," it's "build the
`FinalKGRepository` adapter properly, respect the schema, keep the two repos in sync" — i.e. Path B,
quietly, one correct-feeling commit at a time, each individually justified, none of them required by
what's actually graded. The guardrail is mechanical, not willpower: before touching Learning System
or Research_MCP, decide Path A vs Path B in writing (this doc does that — Path A), and treat any
change that touches `kg_concepts_path`, `vector_snippets_path`, Neo4j, or a second production
adapter as an automatic stop-and-reconsider, not a natural next commit.
