# Interface and Feature Backlog

**Purpose:** Preserve important ideas as separate shippable features without forcing their technical design into the first MVP.

**Implementation status (2026-07-16):** Sections 2 and 3 are available through the shared
`StudyCore` and ten-tool MCP surface. Basic progress includes cards, final-KG coverage, unseen
concepts, due reviews, recent generation/review/practice activity, and active overrides. The
unified chat client owns presentation and answer reveal; it does not duplicate FSRS, generation,
or practice logic. Sections 4–9 remain deferred exactly as sequenced below.

### Promotion record for the chat-experience tier

- **User outcome:** review, generate cards, run temporary campaigns, complete Feynman/challenger
  practice, and inspect basic progress from the unified chat.
- **Owner:** study-system core and MCP adapter.
- **Dependencies:** central study SQLite, read-only final KG/vector adapters, FSRS scheduler, and
  the shared LLM gateway for production generation/evaluation.
- **Data contract:** the ten tools listed in section 2; `study_progress` returns card, coverage,
  unseen, due, generation-run, recent-activity, and active-override data.
- **Acceptance criteria:** adapters share `StudyCore`; writes are idempotent; review changes FSRS;
  practice is grounded and persisted; progress covers every basic count above; baseline remains
  read-only.
- **Preservation impact:** legacy terminal paths remain; no frontend, autonomous director,
  calendar, phone-sync, advanced-learning, or always-on scope is introduced.

## 1. Sequencing rule

Each item below becomes its own implementation plan when promoted. Promotion requires a user outcome, owner, dependencies, data contract, acceptance criteria, and preservation impact.

## 2. Active MVP features

These are planned now in `02_STUDY_AUTOMATION_MCP_AND_CONFIG.md`:

1. Core study service boundary.
2. Automated card-generation runner.
3. Fail-fast shell launcher.
4. Final KG/vector retrieval adapters.
5. Central study SQLite persistence.
6. Due-card and rating MCP tools.
7. Card-generation MCP tool.
8. Safe temporary configuration overrides.
9. Callable Feynman workflow.
10. Callable challenger workflow.

Feynman and challenger remain separate delivery slices even though they are in the same workstream.

## 3. Next tier — chat experience

### Chat-based flashcard review

The unified chat interface presents one card, reveals the answer, accepts a rating, and calls the MCP review tool. FSRS determines due cards.

### Chat-based card generation

The user asks for more cards or a temporary generation campaign. The agent invokes generation or override tools. Baseline values remain protected.

### Chat-based Feynman

The agent selects or accepts a concept, collects the explanation, calls the evaluator, and presents gaps without requiring a separate study-system chatbot.

### Chat-based challenger

The agent manages the question/answer/grading turns through MCP state.

### Basic progress

Expose counts for cards, unseen concepts, due reviews, recent activity, and active overrides. Avoid designing a sophisticated mastery dashboard yet.

## 4. Later — unified frontend features

The frontend is a unified application across systems, not a dedicated study-system app.

Separate future features:

- flashcard pane with reveal/rating controls;
- visual card-generation workflow;
- quiz interface;
- Feynman workspace;
- challenger workspace;
- progress and calibration dashboard;
- automation run history and override controls;
- clickable launcher; and
- agent/action status pane.

The UI calls the same study core through MCP or another supported adapter. It must not recreate FSRS or generation logic in frontend code.

## 5. Later — autonomous director

This requires a dedicated FSRS/mastery design session. Candidate inputs are preserved here without being MVP requirements:

- unseen concept coverage;
- due and overdue FSRS cards;
- recently failed/lapsed cards;
- concept mastery/calibration;
- prerequisite relationships;
- syllabus or learning-goal coverage;
- stale strong-topic verification;
- recent study load;
- explicit temporary topic campaigns;
- exam date and phase; and
- calendar availability.

Do not fit sessions to available minutes in the first version. Do not create strong-topic expiry logic until several months of real review data can inform it.

The existing `SessionPlanner` is reference material for this future feature, not an MVP dependency.

## 6. Later — planner and exam integration

Separate feature slices:

1. Store exam date and static priority.
2. Read availability from the Planner/calendar system.
3. Adjust new-card and quiz intensity.
4. Project coverage against exam date.
5. Recover from missed sessions.

No implementation should start until the basic study automation and review loop are operating.

## 7. Later — phone review and synchronization

The earlier static HTML/iCloud/Gmail approach is parked. When reconsidered, split it into:

1. phone review interface;
2. authenticated or sandboxed result envelope;
3. idempotent importer;
4. transport adapter such as iCloud or Gmail; and
5. conflict/replay handling.

Do not create `Database/Runtime/Exchange` until this feature is promoted.

## 8. Later — advanced learning features

- adaptive quizzes;
- misconception ledger;
- source-change revalidation of cards;
- cross-topic and hidden-link challenges;
- briefing/revision mode;
- strong-topic delayed verification;
- mastery confidence modeling;
- personalized FSRS fitting and rollback;
- workload forecasting;
- learning campaigns with topic filters; and
- research updates that invalidate or supersede learning material.

## 9. Later — always-on operation

When always-on hardware exists:

- run the study core as a supervised local service;
- schedule automation centrally;
- expose authenticated MCP/service endpoints;
- add health checks and alerts; and
- keep baseline configuration protected from agent writes.

## 10. Explicitly retired direction

Unless promoted again, the following are no longer the immediate plan:

- building a standalone study-system FastAPI dashboard;
- using terminal prompts as the normal interface;
- emailing or syncing static HTML decks in the MVP;
- forcing a focus/topic picker before study;
- implementing calendar-aware session fitting now; and
- building a universal taxonomy inside study-system.
