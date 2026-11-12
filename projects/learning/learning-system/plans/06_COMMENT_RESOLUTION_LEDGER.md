# Follow-up Comment Resolution Ledger

**Source:** `REDESIGN_PLAN_v4_FOR_REVIEW.md` through the instruction at approximately line 410 to stop designing later sections  
**Purpose:** Provide a direct answer and destination for every follow-up comment group.

Line numbers are references to the annotated review draft at the time this ledger was created and may move if that document is edited again.

| Source line(s) | Comment or question | Answer/decision | Owning document |
|---:|---|---|---|
| 18 | Study-system may not be user-facing; split automation and MCP; should Feynman/cards be MCP; agent can change temporary policy but not baseline | Agreed with one refinement: create a shared core plus automation and MCP adapters, not duplicate automation/MCP logic. Feynman, challenger, card generation, due review, and ratings become MCP-callable. Agent changes are bounded, audited, expiring overrides; baseline config is protected. | `00`, `02` |
| 18 | Could chat UI have a flashcard pane? | Yes, but it belongs to the future unified frontend. It calls the same study capabilities and is not required for the core MVP. | `05` |
| 20 | Can the capability list be expanded? | Yes: adaptive quizzes, misconception tracking, change-driven revalidation, briefings, hidden-link challenges, workload forecasting, and campaigns are retained as later features. They are not placed in the MVP without separate design. | `00`, `05` |
| 44 | Ingestion should still satisfy study-system's needs while serving all systems | Agreed. Study-system provides consumer requirements; the dedicated unified ingestion system produces shared final knowledge for every authorized consumer. | `03` |
| 52, 54 | Nothing should be stored in this repository; FSRS/card state belongs in Database | Agreed. “Ownership” means exclusive write authority, not physical storage in the repo. All runtime learning data lives in the central study SQLite database. | `00` |
| 56 | Why cache retrieved context instead of getting the latest data? | Remove durable retrieval caching from the MVP. Re-query the final KG/vector stores and retain only source/version references with cards and assessments. | `00` |
| 88 | Study-system should query final KG/vector data, not internal systems | Agreed. Public final-store query interfaces are required. No ingestion staging reads or private implementation imports. | `00` |
| 92 | Removed ingestion responsibilities need a new owner; KG/vector cleaning should be unified | Agreed. A dedicated ingestion project owns capture, structural normalization, hashing, exact dedupe, semantic extraction coordination, and dispatch to KG/vector ingestors. | `03` |
| 101 | Build the best design here, then mutate databases; unsure about engineering approach | Do not mutate real databases first. Define contracts, characterize existing behavior, implement adapters against copies/fixtures, migrate a database copy, validate, then switch configuration with rollback available. | `01`, `03`, `04` |
| 105 | Responsibility tables were unclear | Restated plainly: ingestion writes source/derived knowledge stores; KG owns entity identity; vector owns chunks/indexes; study-system alone writes learning records. Storage is central even though writers differ. | `00`, `03`, `04` |
| 124 | Raw should be above Ingested; what is Exchange? | Adopt `Raw/` and `Ingested/{SQLite,Knowledge_Graph,Vector_DB}`. Exchange was a temporary phone-sync inbox/outbox, not ingested data. It is deferred under `Runtime/Exchange` and is not created now. | `00`, `05` |
| 171 | Separate SQLite storage per project and strict data formats | Agree with separate SQLite **files** per project, strict schemas, and one writer per database. Shared knowledge comes from KG/vector rather than a monolithic SQLite database. | `00` |
| 177 | Identity/taxonomy work belongs to KG and needs a refactor file | Agreed. It is isolated as the KG identity/evolution plan and is not implemented in study-system. | `04` |
| 183 | Is normalization needed if a smart LLM returns strict triplet JSON? | Yes, but separate deterministic structural normalization from semantic interpretation. Strict JSON and temperature zero do not guarantee stable IDs, semantic consistency, provenance, or idempotency. | `03`, `04` |
| 189 | How can aliases be matched without an LLM? | Use stable IDs, exact normalized labels, approved alias edges, deterministic external identifiers, and then similarity/model reasoning only to propose ambiguous candidates. Humans or explicit policy approve uncertain identity. | `04` |
| 191 | Do not let LLM collapse X/Y into Z; link aliases; how does chat feedback update KG/vector; how do beliefs change over time? | Agreed. Preserve nodes and add reviewed `ALIAS_OF`/`SAME_AS` links. Query expands approved aliases. Chat creates a provenance-backed proposal, not a direct rewrite. Vector query expansion indexes aliases. Claims carry time, status, evidence, and supersedes/contradicts links rather than being overwritten. | `04` |
| 195 | Apply earlier alias comments | Incorporated into the link-not-collapse design. | `04` |
| 197 | Meaning of `MERGE` and retaining X's old edges | `MERGE` means idempotent matching by an already-established ID, not semantic collapse. Confirmed identity links make both X and Y neighborhoods retrievable while preserving their original edges. | `04` |
| 206 | Meaning of “must never create a competing concept identity”; how decide alignment? | Study-system never creates KG identities at all. KG assigns a new candidate ID when uncertain and later links identities if confirmed. It uses staged deterministic and reviewed matching, not an impossible exhaustive index. | `04` |
| 228, 235 | The system covers every topic, not only CFA; taxonomy is much harder | Agreed. Reject one mandatory universal hierarchy. Use concepts, claims, provenance, optional broad field tags, graph/vector retrieval, and query-time ranking. Domain-specific taxonomies are optional overlays. | `04` |
| 251 | Who decides taxonomy; maybe concepts and field only; can a smart model at temperature zero handle relevance? | MVP uses concepts, relations/claims, provenance, and optional multi-valued field tags. An LLM may extract and rank relevance at query time, but temperature zero is not a correctness guarantee and cannot enforce identity. | `04` |
| 263, 264 | Stop terminal-based user actions; always use web/chat | Target accepted: no interactive terminal UX. Existing CLI stays temporarily only as compatibility/diagnostic code until MCP/chat replacements pass. | `00`, `01`, `05` |
| 265 | Card and quiz generation functions are important | Preserve and wrap them in the core service. | `01`, `02` |
| 266 | What is the early SessionPlanner? | It is existing code combining due cards, new cards, mastery checks, and exam phase. Preserve as reference; it is not required by the MVP and may be rewritten later. | `00`, `01`, `05` |
| 267 | Feynman/challenger prompts are important | Preserve them and make each a separate callable service/MCP delivery slice. | `01`, `02` |
| 271 | Each major function is a separate shippable feature | Agreed. The backlog separates chat review, Feynman, challenger, quiz, progress, UI, planner, and phone sync. Even active capabilities are split into delivery slices. | `02`, `05` |
| 273, 274 | Park standalone FastAPI app/dashboard; unified frontend later | Agreed. Removed from MVP and recorded as unified frontend work. | `00`, `05` |
| 275-279 | Callable Feynman/challenger, visual generation, phone review, planner are important | Feynman/challenger are active MCP slices. Visual generation, phone review, and planner remain important but are separate later feature plans, not silently dropped. | `02`, `05` |
| 283 | Stick to chat; static HTML send/pull is too complex now | Agreed. Unified chat plus MCP is the immediate interface. Static HTML/iCloud/Gmail is parked. | `00`, `05` |
| 287 | Autonomous system should eventually have UI; do not build sending system now | Agreed. MVP automation is headless and observable through chat/run logs. Unified visual controls are later frontend work. | `02`, `05` |
| 288 | How is explicit review decided? | FSRS determines due cards from their state and due date. Chat requests due cards through MCP; no extra review priority algorithm in MVP. | `00`, `02` |
| 289, 295 | Card amount may have a default/hardcoded policy but agent should change it safely | Put the default once in typed baseline config. Agent creates an allowlisted, bounded, expiring override; it never edits source/config files. | `00`, `02` |
| 290-293 | Feynman, challenger, quiz, progress are important but separate/later | Feynman/challenger are active independent slices. Quiz/chat experience and richer progress are tiered separately. | `02`, `05` |
| 307 | UI buttons later; terminate interactive CLI | Accepted as target. CLI removal occurs after replacement tests, not before. Shell launcher remains non-interactive. | `00`, `01`, `05` |
| 309 | Button and agentic actions may share the same capability | Correct. Future buttons and current MCP tools call the same core services. | `00`, `02`, `05` |
| 316 | `.sh` launcher is important | Included in MVP with environment setup, dependency checks, locking, logging, and fail-fast behavior. | `02` |
| 321 | Clickable launcher is important | Preserved as a future unified frontend/desktop feature. | `05` |
| 322 | Always-on service matters when hardware exists | Preserved as a later deployment feature. | `05` |
| 324 | Launcher must stop on errors | Accepted explicitly. Non-zero exit, no continuation after failed dependencies/steps. | `02` |
| 328 | Earlier application-layer explanation was unclear | Replaced with a concrete diagram: automation and MCP are adapters over one core. No duplicated logic. | `00` |
| 344 | Topic override is future work | Deferred. The only MVP override is safe policy values such as temporary daily count, not topic selection. | `00`, `05` |
| 350-360 | Advanced autonomous inputs are important but later; focus on MVP | Deferred together as the autonomous-director feature. Existing ideas are preserved without burdening MVP. | `05` |
| 372 | Do not fit sessions to today's available time now | Removed from MVP and explicitly deferred. | `00`, `05` |
| 374 | Are machine-readable decision reasons necessary; can they just be logged in SQL? | Use a minimal SQL automation-run audit row. No KG nodes or LLM-generated explanations. This is necessary operational logging for unattended jobs, not a new product surface. | `00`, `02` |
| 393 | Wait for real data before strong-topic verification logic | Agreed. Defer for several months/adequate review evidence. | `05` |
| 405 | Existing planner does not need to be retained unchanged; rewrite from MVP | Agreed. Preserve it as reference/hard work, not as a mandatory production component. Rewrite is allowed after behavior is understood. | `00`, `01`, `05` |
| 410 | Stop designing later technical sections for now | Honored. Later areas are backlog entries only. Active detail is limited to the MVP, preservation, ingestion handoff, and KG refactor requirements raised above this line. | All |

## Net result

The resolved direction is:

> Preserve existing learning logic and data, build a shared study core with automation and MCP adapters, use the unified chat frontend, centralize persistent data outside code repositories, move ingestion into one shared upstream pipeline, leave semantic identity to a non-destructive KG process, and promote later features one at a time.

