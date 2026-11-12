# TODO — Open Items, Assumptions, and Deferred Work

---

## Before First Run (Blockers)

- [ ] Add `ANTHROPIC_API_KEY` to `.env`
- [ ] Add `OPENAI_API_KEY` to `.env`
- [ ] Set `VAULT_ROOT` in `.env` to your actual Obsidian vault path
- [ ] Run `python scripts/bootstrap_db.py` to create the SQLite schema
- [ ] Install dependencies: `uv venv && uv pip install -e ".[dev]"`
- [ ] For quiz MCQ cards: run `study ingest --with-quiz`

---

## Assumptions Baked Into the Code (Need Owner Decision)

### Architecture
- **Shadow-tree layout**: concept directories are written to `STUDY_ROOT` (default `./data/concepts/`). The open question from Ideas.md — `vault/.study/` embedded vs separate repo vs frontmatter-only — is unresolved. Current code uses a separate configurable path.
- **Cost ceiling behaviour**: when monthly spend hits `COST_CEILING_MONTHLY_USD`, the code logs spend but does NOT enforce a hard stop yet. The check is wired in `clients.py` spend logging but there is no gate that blocks further calls. Decide: hard stop mid-ingest, or finish current file?
- **Canonical name collisions**: if two files both mention "Duration", the extractor will create two separate entries. No disambiguation or merge logic exists yet (open question #2 in Ideas.md).
- **Concept rename flow**: renaming a concept in chat is not implemented. All downstream references (cards, atomic facts) would need updating — no UX for this yet (open question #3).
- **Chat history persistence**: the intent classifier prompt has a `{{CONVERSATION_HISTORY}}` placeholder but no storage or pruning logic is wired (open question #4).
- **Multi-device sync**: not addressed. SQLite is local-only (open question #6).

### Quality Sampling
- `GROUNDING_SAMPLE_RATE` and `RUBRIC_SAMPLE_RATE` default to `0.20` (20%).
- Sampling is **probabilistic** (`random.random() < rate`) — non-deterministic.
  If reproducibility is needed, switch to `hash(card.id) % 100 < rate*100` and update
  this note. See `quality.py` module docstring.

### Source Grounding Failure
- A source grounding failure sets `verification_status = 'flagged'`, NOT `'failed'`.
  Flagged cards remain eligible for review (`get_due_cards` filters only `'failed'`).
  This is intentional: a grounding check can be wrong; cards should not be silently
  dropped without human review.

### Models
- Default extraction model set to `claude-sonnet-4-6`. Change in `.env` via `EXTRACTION_MODEL`.
- Card generation uses `gpt-4o-mini`. Change via `CARD_GEN_MODEL`.
- Quiz generation uses `gpt-4o-mini`. Change via `QUIZ_GEN_MODEL`.
- Source grounding + rubric uses `gpt-4o-mini`. Change via `SOURCE_GROUNDING_MODEL`.

### FSRS
- Using FSRS-4.5 default weights (19 floats from py-fsrs reference). Not retrained.
- Retraining trigger (8 months / 1000 reviews) is checked by `maybe_retrain()` but not wired into the app startup loop yet.

### KG
- Cycle detection uses `nx.is_directed_acyclic_graph()` on a copy of the in-memory
  graph before approving an edge. If the KG is large (>10k nodes), consider switching
  to a topological sort check.
- The in-memory NetworkX graph is loaded lazily on first access and kept in sync
  with every subsequent write. It is **not** persisted across process restarts —
  it is always reconstructed from approved edges in SQLite.
- `kg_edges.UNIQUE(subject_id, relation, object_id)` makes `upsert_edge` idempotent:
  re-ingesting the same file will not create duplicate edges.

---

## Incomplete Code Sections

### `store/concept_dir.py`
- `read()` returns a stub `Concept` with empty `summary` and `source_anchors` — it does not parse `_canonical.md` back into a full object. Needed for Phase 2 card regeneration flows.
- `list_by_domain()` uses the slug as the canonical name when reconstructing — will be wrong for multi-word names. Needs a metadata file or SQLite lookup.
- Atomic facts are not parsed back from `atomic_facts.md` (marked `# TODO`). Needed for Feynman mode.

### `clients.py`
- Monthly spend ceiling is logged but not enforced — add a check before each `call()` that raises if `store.monthly_spend() >= config.cost_ceiling_monthly_usd`.

### `ingester.py`
- `scan_vault()` re-writes the manifest hash as a computed sha256 of content on the final `upsert_manifest(..., "processed")` call in `app.py`. This is a best-effort fix; the canonical approach is to carry the body_hash from the scan result through to the final update.

### `scheduler.py`
- `maybe_retrain()` is a stub — always returns `None`. Gradient-based FSRS optimisation not yet implemented.

### `store/vector_store.py`
- `retrieve_atomic_facts_for_concept()` returns an empty list — full reconstruction of `AtomicFact` objects from Chroma metadata is deferred. Use `SqliteStore` for authoritative fact retrieval.

### `quality.py`
- `score_rubric()` uses `source_grounding_model` as the judge model. If you want a separate model for rubric scoring, add `RUBRIC_MODEL` to config and `.env.example`.

---

## Phase 2 Stubs (In Progress / Partially Complete)

- [x] `store/vector_store.py` — ChromaDB integration (lazy import, graceful degradation)
- [x] Source grounding verification per card (`source_grounding_v1.md` wired in `quality.py`)
- [x] Claude-as-judge rubric scoring (`rubric_v1.md` wired in `quality.py`)
- [x] Knowledge graph (`store/kg_store.py` with NetworkX + SQLite)
- [x] Quiz mode (`quiz.py` + `study quiz` CLI command)
- [x] Quiz MCQ card generation (`generator.py::generate_quiz_mcq`)
- [ ] Full LLM attribution validator (`validator_v1.md` prompt exists but calling code not wired)
- [ ] Cross-model consistency sampling
- [ ] Domain-qualified tagging + cosine-similarity dedup on ingest
- [ ] Reminder creation-date tracking in `apple_reminders.py` (see original CLAUDE.md note)

## Phase 3 — Wired (2026-04-27)

- [x] Chat intent router — `chat.py::IntentRouter` + `study chat` CLI command
- [x] Overrides log + consolidation — `overrides.py::OverridesManager`, `study overrides [--consolidate]`
- [x] Director / session planner — `director.py::SessionPlanner + SessionPlan`
- [x] Mastery tracking — `director.py::MasteryTracker + MasteryState`
- [x] Calibration reports — `calibration.py::CalibrationReporter`, `study calibration`
- [x] FSRS auto-retraining check wired to `review` and `chat` startup via `_maybe_retrain_fsrs()`
- [x] FSRS weights persisted in `app_config` table; `study revert-fsrs` command
- [x] Monthly override verification prompt on first session of each month
- [x] Migration 003 for: app_config, chat_history, concept_mastery, fsrs_weights_history, overrides_cache

### Phase 3 Remaining / Known Issues
- [ ] FSRS actual gradient optimisation in `scheduler.py::maybe_retrain()` — still a stub returning None
- [ ] `chat.py::_handle_study()` for Feynman/challenger modes not yet callable (Phase 4)
- [ ] Calibration director integration: overconfident → more quiz, underconfident → more Feynman (used in planner but weak signal until quiz data accumulates)
- [ ] `bootstrap_db.py` needs to be updated to run migration 003 after fresh install

## Phase 4 Stubs (Not Started)

- [ ] Feynman mode (`feynman_evaluator_v1.md` prompt exists, no caller)
- [ ] Challenger mode (`challenger_v1.md` prompt exists, no caller)
- [ ] Hidden-link KG discovery (`hidden_links_v1.md` — prompt not yet written)
- [ ] Feedback propagation (`feedback.py` not created)

## Phase 5 Not Started

- [ ] Briefing mode
- [ ] Planner integration

---

## Prompts Written but Not Yet Wired to Code

| Prompt file | Status |
|---|---|
| `validator_v1.md` | Not wired — `extractor.py` Phase 2 upgrade |
| `source_grounding_v1.md` | **Wired** — `quality.py::check_grounding()` |
| `rubric_v1.md` | **Wired** — `quality.py::score_rubric()` |
| `card_generation_quiz_mcq_v1.md` | **Wired** — `generator.py::generate_quiz_mcq()` |
| `intent_classifier_v1.md` | **Wired** — `chat.py::IntentRouter.classify()` |
| `overrides_consolidation_v1.md` | **Wired** — `overrides.py::OverridesManager.consolidate()` |
| `feynman_evaluator_v1.md` | Not wired — new `feynman.py` (Phase 4) |
| `challenger_v1.md` | Not wired — new `challenger.py` (Phase 4) |

## Prompts Still To Write

- [ ] `hidden_links_v1.md`
- [ ] `cross_model_consistency_v1.md`

---

## Open Questions from Ideas.md (Unresolved)

1. Shadow-tree layout: `vault/.study/` embedded, separate repo, or frontmatter-metadata-only?
2. Canonical-name collision: how is a bare "Duration" attributed when "Macaulay Duration" and "Modified Duration" already exist in the registry?
3. Concept rename UX: user renames in chat — how are all downstream references updated?
4. Chat history persistence: how much history stays in context for intent classifier, and how is it pruned?
5. Cost ceiling behaviour: hard stop mid-ingest, or finish current file and pause?
6. Multi-device sync: if run on two machines, what does sync look like?
