# Study System Redesign Plan v4 — For Review

**Status:** Draft for comment only  
**Written:** 2026-07-14  
**Purpose:** Replace the mental model in `REDESIGN_PLAN.md` with a clearer boundary between ingestion, storage infrastructure, and the user-facing study system.  
**Implementation status:** Nothing in this document is implemented merely because it is written here.

This draft incorporates the comments left in square brackets in `REDESIGN_PLAN.md`. It is intentionally detailed enough to make the important architectural and product decisions explicit before code is changed.

Add comments directly below any `[YOUR COMMENT: ...]` marker. Comments do not need to use a particular format.

---

## 0. Executive decision

Study-system is the **user-facing learning application and learning orchestrator**.

[ITS NOT EVEN USER FACING ANYMORE AS I DONT SEE THE POINT IN IT HANDLING THE FRONT ENED, JUST LIKE WE CREATE A FODLER FOR THE INGESTION, A FOLDER FOR THE DATABASE, A FOLDER FOR INGESTION, SIMILARLY WE SHOUDL CREATE A FOLDER FOR STUDY SYSTEM, I GUESS ITS THE LOGIC. I GUESS THE FOLDER SHOUDL BE DIVIDED IN 2 THE AUTOMATION SIDE, WHICH SHOULD GO IN THE AUTOMATION FOLDER AND THE MCP TOOL SIDE THAT ALLOWS CERTAIN TOOLS TO BE MCP CALLABLE, AS FEYNMAN IS ESSENTIALLY A CHATBOT RIGHT, THEN WHATS THE POINT OF HAVING THE CHATBOT INTERAFCE HERE ? THE FLASHCARD GENERATION IS CERTAINLY SOMETHING UNIQUE TO THIS SYSTEM, BUT SHOUDL THAT BE AN MCP CALL AS WELL ? AND THEN I SCHEDULE THE MCP CALL USING CRON ? OR WE HAVE A DUPLICATE IN THE AUTOMATION FOLDER, I THINK THATS GOOD, THE AUTOMATION FOLDER WORKS BY ITSELF LEARNING FROM FSRS, ITS SHOUDL HAVE A UTILIS FILE AND CONFIG EXPOSING ALL THE CONTROLLING VARIABLES, SO THAT AN MCP CAN WRITE TO IT. EVEN TUAL GOAL FOR AGENT PLATFORM RIGHT ? THEN YOU HAVE THE AUTOMATION SIDE OF THE ODE, WHICH HSOULD RUN BY ITSELF BUT MY AGENT SHOULDNT BE ABLE TO CHANGE THINGS, TRACK IT. BUT ONLY THE BASELINE ASSUMPTIONS, IKE FOR EXAMPLE FOR THE NEXT 14 DAYS, GIVE ME 7 SETS OF FALSHCARDS A DAY INSTEAD OF 5 A DAY, THE UI IN THE CHATBOT ALSO HAVE A PANE FOR SHOWING MY FLASHCARDS, OR SOMETHING LIKE THAT ?]

It is the system you open or call when you want to: [YES ALL GOOD, IS THERE ANYTHIGN WE CAN DO TO EXPAND ON THIS ?]

- start today's automatically selected study session;
- review flashcards using FSRS;
- generate more learning material;
- run a Feynman explanation;
- be challenged with an adversarial or edge-case question;
- take a quiz;
- see mastery, coverage, and upcoming study priorities; or
- let an agent invoke the same capabilities through tools.

Study-system is **not**:

- the raw-data ingestion service;
- the owner of raw source files;
- the process that extracts and deduplicates KG nodes;
- the knowledge graph database;
- the vector database; or
- the abbreviation, spelling, and concept-identity review system.

Study-system consumes stable interfaces from those upstream systems. It owns learning-specific data and behavior that no upstream system should own: cards, FSRS state, reviews, mastery, calibration, session plans, Feynman/challenger attempts, and learning preferences.

**My comment:** This is the most important correction. The previous plan still made study-system orchestrate ingestion and treated it primarily as a thin CLI. That conflated infrastructure with the product you actually use. The revised boundary makes study-system a substantial application while keeping ingestion and storage responsibilities outside it.

[YES BUT THE INGESTION SHOUDL STILL BE DONE THE WAY STUDY SYSTEM WANTS IT TO BE DONE, JUST THAT WE SHOUDL ENSURE THAT THE POINTS AND THW WAY STUDY SSYTEM WANTS THINGS TO BE INGESTED, THATS HOW IT SHOULD BE INGESTED, JSUT THE INGESTED AND STORED FACTS ARE AVAILABLE TO EVERY SYSTEM TO USE NOT JUST STUDY SYSTEM]

---

## 1. System boundaries and ownership

### 1.1 Study-system owns

[BUT NOT STORED HERE, AGAIN, STORED IN DATABASE WHERE ALL THE DATA SHOULD BE STORED, IN THE FINAL DATABASE FOLDER, THE SHOUDLNT BE STORING ANYTHING AT ALL INPUT OR OUTPUT]

[ONLY THE STUDY SYSTEM SHOUDL WRITE THE FSRS, BUT THE CARD STATE SHOUDL BE AGAIN STORED IN DATABASE, AS FOR EVERY OTHER THING HERE]

[AS FOR THE RETRIEVED CONTEXT, SINCE ITS BEEN RETRIEVED BY SYSTEM THAT HAS ALREADY INGESTED THE DATA AND IS FREE TO RETRIEVE, WHY HAVE A CACHE ? JUST RE RETRIEVE IT MAYBE SOMETHIGN HAS BEEN UPDATED THERE, TAKE THE MOST UDPDATED PICTURE YOU HAVE ACCESS TO]

| Capability or data | Ownership rule |
|---|---|
| Flashcards and quiz cards | Created and written by study-system | 
| FSRS card state | Written only by study-system |
| Review history | Written only by study-system |
| Concept mastery and calibration | Calculated and written by study-system |
| Feynman and challenger attempts | Run and stored by study-system |
| Daily session plan | Produced by study-system |
| User learning preferences | Written by study-system |
| Exam-learning priorities | Calculated by study-system from planner inputs |
| Cached retrieved context | Optional, bounded cache owned by study-system |

Study-system may allow other applications to read this data, but it remains the **only writer** to its database tables. External systems should access it through a documented API, MCP tool, or read-only connection rather than writing directly to its SQLite file.

### 1.2 Upstream systems own

| Capability or data | Owner |
|---|---|
| Capturing raw information | Ingestion system |
| Immutable raw/bronze records | Raw-data store |
| Triplet and relationship extraction | KG ingestion pipeline |
| Concept identity and aliases | KG ingestion pipeline |
| KG node deduplication | Knowledge-graph layer |
| Embedding and chunk creation | Vector ingestion pipeline |
| Knowledge graph | Neo4j/KG service |
| Vector index and source chunks | Vector DB service |
| Abbreviation and spelling review | Ingestion review component |

Study-system should not import or call internal implementation classes from these projects. It should use stable service or MCP contracts so that upstream storage can change without forcing a study-system rewrite.

[WELL I DONT THINK I FULLY UNDERSTAND WHAT YOU MEAN BY THIS, STUDY SYSTEM SHOUDL CALL THE FINAL KG, QUERY IT, NO POINT IN GETTING INFORMATION FROM THE INTERNAL SYSTEM, IF STUDY SYSTEM NEEDS SOME INFORMATION THEN ITIS THE KG OR VECDB OR SQL LITELTABLES JOB TO MAKE SURE ITS STORED AND EXPOSED SO READING TOOL CALLS IS NOT SOMETHIGN THATS BEING DONE]

### 1.3 What moves out of the current repository design

The following current responsibilities should be removed from study-system after replacement interfaces exist: [BUT THE RESPONSISIBILITY SHOULD BE PASSED ON TO SOMEONE ELSE, ITS NOT THAT THIS SHOULDNT BE DONE AT ALL, JUST THAT ITS NOT STUDY SYSTEMS JOB TO DO IT, WHAT SHOUDL DO IT EXACTLY YOU TELL ME, I THIN THE MAJOR ISSUE OF DIFFERENT PIPELINES FOR KG AND VECDB INGESTION IS ALSO NOT GOOD, YOU SHOULD HAVE A UNIFIED INGESTION PIPELIEN IN ERMS OF DATA CLEANING ETC, ONCE YOU ARE READY WITH INGESTION THAT INCLUDES, HASING ETC, THEN KG AND VECDB SHOULD INGESTION, AND THE DATA SHOULD BE PASSED TO THEIR RESPETIIVE INGESTOR]

- scanning the source vault;
- reading and hashing raw files;
- extracting concepts directly from files;
- creating local KG edges;
- embedding extracted source material; and
- maintaining source-ingestion manifests.

Removal must happen only after the shared ingestion pipeline and retrieval contracts are proven [THIS WILL HAVE TO BE BUILT ONCE WE ARE AHPPY HERE I WIL GET THOSE BUILT, BUT I DO THINK WE SHOULD DO THE BEST JOB HERE AND THEN MUTATE THE DBS TO ALIGN WITH THIS, HOWEVER I HAVE NO IDEA ABOUT ADVANCED SOFTWARE ENGINEERING SO I AM OPEN TO SUGGESTIONS HERE ]. Old paths should not be deleted first and replaced later.

**My comment:** Your instruction that ingestion is “not your problem” is correct as a product boundary. Study-system still needs to document what it expects upstream, but that is an interface contract, not ownership of ingestion.

[YOUR COMMENT: Are any responsibilities in the two ownership tables assigned to the wrong system?: NOT SURE WHAT YOU MEAN SO OPEN TO SOME SUGEGSTIONS]

---

## 2. Canonical database and folder structure

### 2.1 Canonical study-system path

The study-system database will live at:

```text
<AI Code>/Database/SQLite/study_system/study_system.db
```

It will not live inside the study-system code repository.

### 2.2 Recommended shared database root

```text
[RAW AND REST SHOULDNT STAY ON THE SAME LEVEL THEY SHOULD BE LEVEL DONE FROM RAW, I THINK BECAUSE THAT MAKES LOGICAL SENSE TO ME, DOES IT TO U? IT SHOULD RAW AND INGESTED AND IN INGESTED YOU HAVE THE REST. HOWEVER I DONT UNDERSTADN WHAT  EXCHANGE HERE DOES ?]

<AI Code>/Database/
├── Raw/
│   ├── immutable/
│   └── manifests/
├── SQLite/
│   └── study_system/
│       ├── study_system.db
│       └── backups/
├── Knowledge_Graph/
│   ├── data/
│   └── backups/
├── Vector_DB/
│   ├── data/
│   └── backups/
├── Exchange/
│   └── study_system/
│       ├── outbound/
│       ├── inbound/
│       └── quarantine/
└── Backups/
    └── manifests/
```

The exact on-disk folders used by Neo4j and the vector database may be governed by those engines. The important rule is that their persistent data has a deliberate home under the shared database root or a documented external engine path; it is not mixed with application source code.

### 2.3 Code and data separation

Ingestion **code** belongs in its own application or repository. Raw data and generated database files belong under the database root. A folder called `Database/Ingestion` should not become a home for executable application code merely because ingestion writes data.

### 2.4 Configuration

The physical path must come from one shared configuration value rather than being repeated throughout the codebase. The application should fail clearly if the configured database root is missing or not writable. It must not silently create a second database inside the repository.

### 2.5 Backup rule

A central folder makes backup simpler, but one filesystem copy is not a backup. The minimum policy is:

- create a timestamped SQLite backup before migrations and bulk imports;
- use SQLite's backup mechanism rather than copying a database during an active write;
- keep a small rotating set of recent local backups;
- maintain a manifest recording schema version, backup time, and file checksum; and
- separately back up the shared database root to another device or backup service.

**My comment:** Centralizing persistent data is a good decision. The protection comes from central location plus strict ownership, correct backup procedures, and documented interfaces. Allowing every project to write into the central SQLite file would make the system more fragile, not less.

[I AGREE, SO WHY DONT HAVE A SQLLITE TABLE FOR EACH PROJECT, BUT IDEALLY WE SHOULD CREATE A PIPELINE FOR DATA FOR EXAMPLE, A STRICT FORMAT AND WRITE TYPE THAT MAKES THE SYSTEM LESS FRAGILE, BUT FOR SQLLITE TABLES I DONT MIND HAVING A FEW AS I DONT GAIN ANYTHIGN FROM COMMON LEARNING THAT KG AND VECDB WONT GIVE, DO YOU AGREE ?.]

---

## 3. Concept identity, deduplication, topics, and domains

[THIS IS THE KGS DOMAIN, I THINK WE CAN LOOK INTO THSIS BUT IT SHOUDL BE COLLATED AS A FILE TFOR ME TO HAVE WHEN I AM LOOKING AT REFACTROING THE KG TO ALIGN WITH THIS PORJECT]

This is an upstream requirement, but it must be resolved because study-system depends on stable concept IDs.

### 3.1 Duplicate prevention

[THE NORMALISATION IS NEEDED ? IF WE PASS THE CONTENT TO AN LLM TO GIVE TRIPETS A SMART ONE, AND ASK IT TO RETURN THE TRIPLETS IN A SPECIFIC JSON FORMAT, THEN INGEST THAT ? ]

A separate “check whether this node exists” file is not enough. Duplicate prevention must be enforced at several levels:

1. **Normalize the candidate:** trim whitespace, normalize casing and punctuation, expand reviewed abbreviations, and preserve the original label as an alias.
2. **Resolve aliases:** check whether the candidate is an approved alias of an existing concept.
[THIS IS A BIT MORE COMPLEX HOW DO YOU DO THIS WITHOUT THE LLM?]
3. **Use domain-qualified identity:** avoid assuming that the same word always means the same concept across domains.
[MY ISSUE EXACTLY HOW DO YOU DECIDED EVERYTHING MEANS THE SAME THING IN EVERY FIELD ? THIS IS THE ISSUE WITH ALISAES, YOU ARE LEAVNING IT UP TO THE LLM TO DECIDE, AND MAKE DATA DECISION THAT I DONT HTINKYOU SHOUDL DO EVEN IF ITS AN ALIS, ALL THAT MATTER SIS THAT YOU LINK IT, TO THE OTHER ALISAE, YOU LINK X AND Y WHEN THEY AREALISAES AND THEY ARE NOW RETRIEVABLE INFORMATION INSTEAD OF MUTATING X AND Y INTO Z SO THAT HTYE  MEAN THE SAME, I JSUT DONT KNOW IF WE SHOULD TRUST THE LLM TO DO I , NOT HAT IT WONT BE ABLE TO DO IT, BUT YOU KNOW AS A DEICSION, INSTEAD ALISA LOOKING SHOUDL HAPPEN WHEN WE QUERY THE KG YOU SHOULD WRITE A QUERY WHICH LOOKS FOR NKNOWN ALISES, AND PULL THE INFROMATION INSTEAD OF DOING IT AT INPUT, NOW ONE QUESTION ARISES IS, HOW DO YOU FEED INFORMATION FROM THE AGENTS CHATLOG BACK TO THE KG ONCE I ACKNOWLEDGE THAT THESE ARE ALIASES IS THE LINK BUILT IN THE KG AND VECDB, IS IT INDECEXED IN THE VECDB AND HOW IS IT THAT WE DO THIS ? ALSO HOW DO WE BUILD A TIME WEIGHTAGE IN TO THIS THINGS ARE PROVEN WRONG ALL THE TIME,A ND YOU KNOW I AM BUILDING RESEARCH TOOLS FOR THIS BUT HOW DO YOU CHANGE BELIEVFS ?]

4. **Match conservatively:** use exact keys first, then alias matches, then similarity as a proposal requiring review when confidence is insufficient.
5. **Enforce a database constraint:** the KG must have a uniqueness constraint on its canonical identity key.
[LOOOK AT COMMENTS ABOVE]

6. **Write idempotently:** use the KG equivalent of `MERGE`, not unconditional node creation. [WHEN YOU SAY MERGE YOU MEAN TRIPELTS SHOUD SPAWN FORMO THIS, IF X ALREADY EXISTS AND WE ARE INGESTING Y IS REALTED TO A AND X AND Y ARE THE SAME NODE EXACT SMAE NODE, THEN X SHOUDL CONNECT TO ALONG WITH ITS ALREADY EXISTING NODES (X'S EXISTING NODES)]
7. **Preserve provenance:** record which source and extraction proposed each alias, classification, and relationship.

A useful canonical identity shape is:

```text
concept_key = taxonomy_id + canonical_slug
```

If no external taxonomy ID exists, the KG service should create and retain a stable internal ID. Study-system mirrors that stable ID and must never generate a competing concept identity. [WHAT DOOES THIS MEAN ? WHAT DO YOU MEAN MUST NEVER GENERATE A COMPETING CONCEPT IDENTITY ? AS IN A COMPETING CONCEPT SHOULDNT BE CREATED ? BUT AGAIN HOW DO YOU DECIDE THIS ? HOW DO YOU DECIDE WHAT CONCEPT ALIGNS WITH WHAT ? AGAIN I DONT UNDERSTAND, MAYBE BASED ON AN EXTENSIVE LIST OF INDEXES ?]

### 3.2 Topic and domain extraction

Topic/domain classification should be produced during the same semantic extraction process that produces concepts and triplets. It should not be an unrelated second interpretation of the source.

The extractor should return something equivalent to:

```json
{
  "concept": "Modified Duration",
  "taxonomy_path": ["CFA", "Fixed Income", "Bond Valuation", "Interest Rate Risk"],
  "domain": "Fixed Income",
  "aliases": ["mod duration"],
  "relationships": []
}
```

### 3.3 Controlled taxonomy

The model should classify against a controlled, versioned taxonomy. It should not freely invent top-level domains on every extraction.

For CFA material, the preferred authority order is: [NO BUT THATS THE ISSUE THIS SI NOT LIMITED TO CFA MATERIAL, IT COULD BE ANYTHING, RANGING FROM ANY TOPIC UNDER THE SUN, YOU CANT COME UP WITH A 4 STEP PLAN FOR EVERY TOPIC UNDER THE SUN OR EVERY TOPIC I READ ABOUT]

1. official CFA curriculum structure;
2. an approved local extension to that structure;
3. reviewed aliases and mappings learned during ingestion; and
4. model-proposed new categories held for review, not immediately accepted.

The web can help discover or seed public taxonomies, but web results should not automatically rewrite the canonical hierarchy. Curriculum versions also need to be recorded because topic structure can change between exam years. [COMMENTS ABOVE HAS TO BE A DEEPER MORE COMPLICATED THING]

### 3.4 Contract required by study-system

Study-system needs the upstream concept service to guarantee:

- stable `concept_id` values;
- canonical name;
- taxonomy path and domain;
- aliases where available;
- source references;
- last-updated timestamp or version; and
- an idempotent list/change-feed interface.

**My comment:** Your questions exposed a real missing dependency. Mirroring concept names is only safe if the KG already guarantees identity. The study-system mirror should not become a second deduplication engine.

[LARGER QUESTION OF WHO DECIDES ON THE TAXONOMY ? THIS IS BIGGER THING MAYBE WE SHOUDL STICK TO DEFINIING THE CONCEPTS AND THE FIELD AND THTS IT NO DOMAIN, OR INDUSTRY OR SUB TOPIC OR ANYTHING THAT SPECIFIC RETRIEVAL, EXTRACTS ALL THE POSSIBLE INFORMATION, AND FILTERS, THE LLM THEN DECIDES WHAT IMPORTANT I THINK, I DONT KNOW WHAT LEVEL YOU GO TO TO BE HONEST ACCURATELY, BUT I GUESS THE THING IS THERE IS A COMPLEX SOLUTION THE EASIER SOLUTION MAYBE JUST RELY ON THE SAMRT LLLM MODELS WE ARE USING, THEY ARE SMART ENOUGH TO DO THIS AT TEMPERATURE 0 WHAT DO YOU THINK ?]

---

## 4. The application that must exist

### 4.1 Current reality

The required application does not currently exist in this repository.

What exists today:

- terminal flashcard review; [ALL TERMINAL BASED ACTIONS ARENT REQUIRED ANYMROE, WE SHOULDNT BE DOING AYTHING BASED OF TERMINAL ANYMORE, WE SHOUDL ALWAYS BE USING THE WEB INTERFACE, EVERYTHING.]
- terminal chat/intention routing; [SAME AS ABOVE]
- card and quiz generation functions; [YES IMPORTANT]
- an early session-planning class; [NOT SURE WHAT THIS IS]
- Feynman and challenger prompt templates. [YES VERY IMPORTANT]

What does not exist today:

[ALL THE IMPORTANT THINGS ARE IMPORTANT BUT THEY ARE ALL SEPERATE SHIPPABLE THINGS, ALL OF THEM EXTREMELY SEPERATE]

- a FastAPI/HTML study-system application; [PARK THIS FOR NOW, AS IN I WANT TO BUILD A UNIFIED FRONT END INTERFACE, USING ALL THE VARIOUS COMPONENTS A UNIFIED INTERFACE IS IMPORTANT]
- a button-driven study dashboard; [AGAIN PARK THIS, THIS IS FOR LATER]
- a callable Feynman workflow; [YES IMPORTANT]
- a callable challenger workflow; [YES IMPORTANT]
- a visual flashcard generation workflow; [YES IMPORTANT]
- a phone-ready review and results-sync workflow; and [YES IMPORTANT]
- complete planner/calendar integration. [YES IMPORTANT]

### 4.2 Proposed application

Build a local study-system application with one primary screen. The first and clearest action is **Study now**. The application selects the session; the user should not need to configure a topic before starting. [ACTUALLY, LETS STICK TO THE CHAT INTERFACE, AS I FEEL THE HTML AUTOMATION SENDDING AND PULLING INFORMATION IS TOO COMPLICATED, ITS IMPORTANT BUT FOR LATER I FEEL, NOT RIGHT NOW]

Primary actions:

- **Study now:** run the autonomous plan for today. [THE AUTONOMOUS SYSTEM SHOULD BE A UI, NOT THE SENDING SYSTEM WE HAD PLANNED FOR NOW,ADDED COMPLEXITY NOT REQUIRED RIGHT NOW]
- **Review:** explicitly run due cards if desired. [HOW DO WE DECIDE THIS ?]
- **Generate cards:** generate an additional chosen quantity. [IMPORTANT FOR LATER, SHOULD BE IMPORTANT TO HAVE THE CONFIG ETC]
- **Feynman:** choose or receive a concept, submit an explanation, and receive gap analysis. [IMPORTANT FOR CHATBOT, IMPORTANT FOR LATER, NEEDS TO BE FIGURED OUT]
- **Challenger:** receive a difficult question, answer it, and receive grading. [IMPORTANT FOR LATER]
- **Quiz:** run an exam-style question session. [IMPORTANT FOR LATER]
- **Progress:** see coverage, due work, mastery, calibration, and exam trajectory. [IMPORTANT]

The interface should expose a simple card-count control for deliberate generation, such as 5, 10, 20, or a custom value. Five must not remain hardcoded. [IT MAYBE SHOULD BE HARDCODED, BUT IT SHOULD BE EXPOSED IN A WAY, THAT AGENT CAN CHANGE IT]

### 4.3 One capability layer, several interfaces

Application buttons, CLI commands, agent messages, and future MCP tools must call the same underlying Python service functions. Business logic must not be duplicated inside HTML handlers or shell scripts.

```text
UI button ───────┐
CLI command ─────┼──> StudyService capability methods ──> database/retrieval
Agent/MCP tool ──┘
```

[UI BUTTON LATER, CLI COMMAND NEEDS TO BE TERMINATED FULL STOP]

This allows permanent button-based control without preventing agentic operation. [I GUESS YES, AGENTIC BUTTON IS THAT I GUESS.]

### 4.4 Startup experience

Short term:

- provide one stable command that starts the local application;
- optionally provide a small `.sh` launcher that activates the environment and runs that command; and [YES THIS IS IMPORTANT, THIS NEEDS TO BE DONE, THE .SH FILE FEELS LIKE ITS THE RIGHT DIRECTION, INSTEAD OF A SIMPLE PYTHON FILE, THEREFORE THE .SH FILE CAN EASILY RUN FRMO TERMINAL INSTEAD OF OPENING IDE OR SOMETHING, MAKING IT A SIMPLE CALL AWAY, I CAN ALSO BUILD ON THIS MORE]
- open or print the local application address.

Long term:

- provide a normal clickable launcher/application entry point; and [YES DEFINITELY, VERY IMPORTANT]
- optionally run a local background service so agent and MCP capabilities are ready without manual startup. [EVENTUALLY EVENTUALLY YES, IMPORTANT BUT FOR WHEN I HAVE A HARDWARE THAT IS ALWAYS ON]

The `.sh` file is a launcher, not the application architecture. Failures during its startup sequence must stop the sequence and display the failing step; it should not continue and present partial output as success. [ABSOLUTELY YES]

**My comment:** A general chat frontend elsewhere cannot be counted as the study-system UI unless it actually implements these workflows and states. The clean approach is a study-system application over a shared capability layer.

[YOUR COMMENT I DONT REALLY UNDERSTAND TBH]

---

## 5. Autonomous daily study selection

### 5.1 Default behavior

The default must be zero-decision:

```text
Open application -> click Study now -> session begins
```

The application, not the user, chooses the concepts and modes for the normal daily session.

A manual topic override may exist under an advanced/custom-session path. It is an escape hatch, not a required focus picker and not part of the default flow. [TOOPIC OVVERIDE IS NOT SOMETHING WE SHOULD LOOK INOT RIGHT NOW IMPORTANT FOR THE FUTURE]

### 5.2 Inputs to the daily director

The autonomous director should consider:

- overdue and due FSRS cards; [YES FOR LATER, IMPORTANT BUT FOR LATER, LETS KEEP FOCUSED ON THE FIRST SOLUTION WE WANT TO MAKE, MVP OUT THEN TIERED IMPORVEMENTS]
- unseen concepts; [IMPORTANT]
- mastery and calibration by concept; [IMPORTANT]
- syllabus coverage; [IMPORTANT]
- concept importance and prerequisites; [IMPORTANT, BUT FOR KATER THIS REQUIRES A DETAILED LOOK AT FSRS, NOT ENTIRLEY SURE WHATS THE PLAY HERE]
- exam date and current exam phase; [IMPORTANT, BUT FOR LATER I THINK]
- upcoming calendar availability; [IMPORTANT, BUT FOR LATER]
- recent study load and session length target; [IMPORTANT]
- recently failed or repeatedly lapsed material; [IMPORTANT BUT ONCE WE HAVE FSRS RIGHT? ]
- stale “strong” concepts that need verification; and [YES BUT AGAIN NEEDS FSRS ?? HOW DO YOU KNOW ITS WORKING AND WHATS THE LOGIC FOR IT?]
- explicit temporary overrides when the user supplies one. [IMPORTANT, FOR LATER]

### 5.3 Priority order

The first practical selection policy should be deterministic and inspectable:

1. Include overdue reviews.
2. Include due reviews.
3. Add exam-critical weak concepts.
4. Add previously introduced concepts with low mastery.
5. Introduce a capped number of unseen concepts for coverage.
6. Add occasional verification of apparently strong concepts.
7. Fit the final plan to today's available time. [NOT REQUIRED, AS THIS BUILD CONSTRAINTS THATS NOT NECESSARY AND FUCK UP THE IMPLEMENTATION]

Every selected session item should retain a short machine-readable reason, such as `overdue`, `weak_exam_priority`, `new_coverage`, or `mastery_verification`. This makes autonomous decisions auditable. [IS THIS NECESSARY ? REALLY NECESSARY ? FEELS LIKE ANOTHER SURFACE TO BREAK, CAN WE NOT JUST LOG IT IN THE SQL BACKEND OR THE IN THE GRAPH NODES OR WAHTEVER ? AND RE RED EVERYTIME]

### 5.4 Cold start and the first 1,000 reviews

FSRS does **not** need 1,000 reviews before it can schedule cards. It can schedule from the first review using default model weights. The 1,000-review threshold is relevant to personalized weight fitting, not to activation of spaced repetition.

New concepts should have an explicit state such as `unseen`, not a fabricated performance score. A safe cold-start loop is:

```text
Day 1: select unseen concepts -> generate/retrieve cards -> first reviews
Day 2: serve due cards -> introduce more unseen concepts within the daily cap
Later: continue due reviews + controlled new coverage
After sufficient history: fit personalized FSRS weights
```

Starting with five unseen concepts per day is reasonable as a default, but it must be configurable. The daily count should adapt downward when the due-review burden becomes high and can adapt upward when there is capacity.

### 5.5 Preventing strong topics from disappearing forever

A concept that scores strongly on first exposure should not be treated as permanently mastered. Use: [THEREFORE WE CAN WAIT FOR A FEW MONTHS, INSTEAD OF BUILDING LOGIC FOR THIS RIGHT NOW, THE REST OF THE KINKS WE CAN WORK OUT IN DEPTH]

- FSRS-scheduled card reviews;
- a separate concept-mastery confidence value;
- delayed verification after a strong first result;
- mixed question types, including recall, application, Feynman, and challenger; and
- an upper bound on how long any exam-critical concept can go without verification.

Card memory and concept mastery are related but not identical. One strong flashcard response should not assign “80 mastery” to an entire topic.

### 5.6 Existing foundation

The repository already contains an early `SessionPlanner` that selects due reviews, new cards, mastery verification, and exam-phase-dependent quizzes. It should be retained as a starting point but revised to use the new storage/retrieval interfaces and real planner/calendar inputs. [NOTHING SHOULD BE CONTAINED YOU CAN REWRITE EVRTHING BUT WE START FROM THE MVP]

**My comment:** Your zero-friction goal is correct. The manual focus picker should be removed from the main flow. The key refinement is to distinguish “unseen,” card-level FSRS state, and topic-level mastery rather than treating all three as one score.
---

[FROM THIS POINT ON, I WANT YOU TO FOCUS ON THE COMMENTS ABOVE AND THEN LATER WE CAN FOCUS ON IT AS AND WHEN REQUIRED. BECAUSE IIT SEEM SLIKE TECHNCIAL DETAILS FOR A THINK I AM NOT EVEN SURE I WANT TO BUILD JUST YET ]

## 6. Flashcard generation and lifecycle

### 6.1 Generation should not be tied to ingestion

Cards are generated by study-system when its learning plan needs them or when the user explicitly requests more. Upstream ingestion should make knowledge available; it should not force card generation.

### 6.2 Generation request

A generation request should specify:

```json
{
  "concept_ids": ["stable-upstream-id"],
  "count": 10,
  "card_types": ["recall", "application"],
  "difficulty_target": "mixed",
  "reason": "new_coverage"
}
```

The autonomous director supplies these values during normal operation. The user may change count and type in the explicit Generate Cards workflow.

### 6.3 Quality and duplication controls

Before a new card becomes reviewable, study-system should:

- confirm that its answer is grounded in retrieved source chunks;
- retain source references;
- reject malformed cards;
- compare against existing cards for the same concept;
- avoid near-duplicate questions testing the same fact in the same way; and
- record generation model and prompt version.

### 6.4 Building toward a large collection

The system may ultimately contain 1,000 or more cards, but generating 1,000 cards blindly at setup is not required and may create low-value duplication. Prefer progressive generation based on syllabus coverage, prerequisites, exam importance, and gaps revealed during study.

A coverage dashboard should show:

- concepts with no cards;
- concepts with insufficient card variety;
- concepts with unverified cards;
- concepts never reviewed; and
- high-priority syllabus areas below target coverage.

**My comment:** The goal should be a broad, high-quality collection, not an arbitrary initial batch size. Progressive generation allows review evidence to influence what gets created next.

[YOUR COMMENT: Should the system also support an explicit “build initial card bank” operation with a target such as 1,000 cards?]

---

## 7. Feynman and challenger workflows

### 7.1 Feynman workflow

Input:

```json
{
  "concept_id": "stable-upstream-id",
  "explanation": "user explanation",
  "session_id": "study-session-id"
}
```

Output and stored result:

- what was explained correctly;
- missing atomic facts or relationships;
- misconceptions;
- clarity and completeness grading;
- follow-up question where useful;
- source references used for evaluation; and
- mastery evidence produced by the attempt.

### 7.2 Challenger workflow

The system retrieves the concept context, generates an edge case or adversarial question, accepts the user's answer, grades it against grounded knowledge, explains the gap, and stores the attempt as mastery evidence.

### 7.3 UI requirement

Both modes require purpose-built interaction states in the study application. A prompt file and a generic chat box are not a completed workflow.

### 7.4 Tool requirement

Once the callable service functions are stable, expose them as MCP tools so an agent can say, for example, “challenge me on something I am weak at.” The UI and MCP tool must use the same evaluation implementation.

**My comment:** These are core study-system capabilities, not parked integrations. Their UI and callable implementations belong in the active build plan.

[YOUR COMMENT: Should Feynman/challenger be included in the first usable application release or immediately after flashcard review?]

---

## 8. Planner and exam-priority integration

Planner integration is active scope.

### 8.1 Minimum planner inputs

- exam name and date;
- syllabus or taxonomy version;
- study availability by day;
- blackout dates or calendar conflicts;
- optional target session length; and
- priority overrides when explicitly supplied.

### 8.2 Responsibilities

The Planner/calendar system owns calendar events and availability. Study-system owns the learning decision: which topics, cards, and modes best fit the available time and exam objective.

### 8.3 Initial integration

Do not wait for a perfect Planner application. Start with a small interface that can provide:

```json
{
  "exam_date": "YYYY-MM-DD",
  "available_minutes_today": 45,
  "available_minutes_next_7_days": [45, 30, 0, 60, 45, 90, 90]
}
```

Study-system can then change new-card caps, review intensity, quiz frequency, and content priority according to exam proximity and available time.

### 8.4 Later integration

Later versions can add:

- calendar event creation;
- missed-session recovery;
- weekly coverage targets;
- workload smoothing;
- projected syllabus completion; and
- alerts when the current pace is insufficient.

**My comment:** The existing session planner means this is not a blank start. The right first step is a small input contract, followed by deeper Planner integration when the planner project supports it.

[YOUR COMMENT: Which planner/calendar is the intended source of exam date and daily availability?]

---

## 9. Phone delivery, result synchronization, and sandboxing

### 9.1 Principle

Transport choice comes after the result contract and sandbox. iCloud Drive, Gmail, or another transport must not be allowed to write arbitrary data directly into the learning database.

### 9.2 Exchange sandbox

Use dedicated directories:

```text
Database/Exchange/study_system/
├── outbound/
├── inbound/
└── quarantine/
```

Rules:

- outbound files are generated only by study-system;
- inbound files are treated as untrusted data;
- only approved filename patterns and file sizes are accepted;
- results use a versioned JSON schema;
- session and card IDs must exist;
- ratings must be within the allowed enum;
- imports are idempotent by `session_id` plus result ID;
- malformed or suspicious files move to quarantine;
- imported content is never executed;
- paths inside imported content are ignored; and
- database writes happen in a transaction after full validation.

### 9.3 Recommended result envelope

```json
{
  "schema_version": 1,
  "session_id": "uuid",
  "exported_at": "ISO-8601 timestamp",
  "results": [
    {
      "result_id": "uuid",
      "card_id": "uuid",
      "rating": 3,
      "answered_at": "ISO-8601 timestamp"
    }
  ]
}
```

The actual implementation may add a signature or keyed integrity check if files cross a less trusted transport.

### 9.4 Transport phases

1. Validate local export and import using files in the exchange sandbox.
2. Add iCloud-synced delivery if it meets the device workflow.
3. Add Gmail ingestion only if email materially improves the experience.
4. Move to a direct authenticated local service later if reliable phone-to-Mac connectivity is available.

### 9.5 Gmail comment

Gmail automation may not require much code, but code volume is not the deciding factor. Duplicate messages, malformed attachments, permissions, sender validation, and replay protection must be handled. Gmail should be treated as a transport adapter over the same validated importer, never as a privileged database writer.

**My comment:** Your sandbox requirement is non-negotiable and should be part of the first sync design, not a later hardening task.

[YOUR COMMENT: Is iCloud still the preferred first phone transport, or should Gmail be tested first?]

---

## 10. Proposed build sequence

### Phase 0 — Confirm contracts and protect existing behavior

- Approve this scope and ownership model.
- Confirm the canonical database path.
- Inventory current working study behaviors.
- Define upstream concept/retrieval interfaces.
- Define the study-system service layer.
- Add tests around current scheduling and database behavior before migration.

**Done when:** responsibilities, paths, contracts, and migration safety are explicitly approved.

### Phase 1 — Separate storage and learning capabilities

- Move/configure study-system SQLite at the canonical path.
- Add safe migration and backup handling.
- Introduce service functions for card generation, review, and session planning.
- Make card count configurable.
- Stop new learning workflows from depending on ingestion internals.

**Done when:** existing terminal review works against the central database and capability methods can be called without invoking ingestion.

### Phase 2 — First usable application

- Build the local application shell.
- Add Study Now.
- Add flashcard review and rating persistence.
- Add explicit Generate Cards with count controls.
- Add basic progress/coverage status.
- Provide one-command and clickable startup paths.

**Done when:** the normal daily workflow can be completed through buttons without terminal interaction.

### Phase 3 — Autonomous director and cold start

- Remove the focus picker from the default path.
- Implement due/overdue/new/weak/verification selection priorities.
- Add unseen-concept introduction.
- Store decision reasons.
- Add session-length constraints.

**Done when:** clicking Study Now reliably creates a justified session without asking the user to choose a topic.

### Phase 4 — Feynman and challenger

- Implement callable Feynman evaluator.
- Implement callable challenger workflow.
- Add both application interfaces.
- Feed results into mastery carefully.
- Add MCP tools over the same capability methods.

**Done when:** both modes run end to end, remain grounded, store attempts, and affect mastery evidence.

### Phase 5 — Planner/exam integration

- Accept exam date and availability inputs.
- Adjust study load and topic priority.
- Add exam-trajectory and coverage views.
- Integrate with the Planner project through a stable contract.

**Done when:** today's study plan changes appropriately with exam proximity, syllabus gaps, and available time.

### Phase 6 — Phone sync sandbox

- Implement the versioned result envelope.
- Implement validation, idempotency, and quarantine.
- Test local file round trips.
- Add the chosen iCloud or Gmail transport adapter.

**Done when:** a phone session can update FSRS state without manual data editing and duplicate delivery cannot duplicate reviews.

### Phase 7 — Personalized FSRS and deeper automation

- Fit personalized FSRS weights after sufficient review history.
- Validate new weights before activation.
- Add rollback.
- Improve workload forecasting and agent-initiated sessions.

**Done when:** retraining is measurable, reversible, and demonstrably better than the default weights.

[YOUR COMMENT: Reorder phases here if Feynman/challenger, planner, or phone delivery must arrive earlier.]

---

## 11. Decisions proposed by this draft

1. Study-system is a user-facing learning application and orchestrator.
2. Ingestion and shared storage construction are outside its ownership.
3. Study-system is the exclusive writer of its learning-state database.
4. The database path is `<AI Code>/Database/SQLite/study_system/study_system.db`.
5. Concept IDs and deduplication are guaranteed upstream.
6. Topic/domain classification uses a controlled, versioned taxonomy.
7. The required button-based application does not exist and must be built.
8. Study Now selects content autonomously by default.
9. Manual topic selection is an advanced override, not a required step.
10. FSRS begins with the first review; 1,000 reviews apply only to personalized fitting.
11. Unseen concepts are introduced gradually with a configurable daily cap.
12. Card count is configurable and no longer hardcoded to five.
13. Feynman and challenger are active study-system capabilities.
14. Planner/exam-priority work begins through a small interface now.
15. Phone synchronization is built over a validated exchange sandbox.
16. Gmail and iCloud are transport adapters, not trusted database writers.

[YOUR COMMENT: Mark any numbered decision you reject or want changed.]

---

## 12. Open questions requiring your decision

1. Is five unseen concepts per day the correct initial cold-start default?
2. Should “build initial card bank” exist as a separate bulk operation, and should it target 1,000 cards?
3. Should Feynman/challenger ship in the first application release or immediately afterward?
4. Which Planner/calendar project should supply exam date and availability?
5. Should the first phone transport trial use iCloud or Gmail?
6. Should non-CFA learning use one global taxonomy registry or separate domain-specific registries?
7. Which progress measures matter most on the first dashboard: due count, coverage, mastery, exam trajectory, time studied, or another measure?
8. Should other systems receive read access through an API/MCP tool only, or is a documented read-only SQLite connection also acceptable?

[YOUR COMMENT: Answer any questions now; unanswered questions remain open and must not be silently decided during implementation.]

---

## 13. One-paragraph version

Study-system is the application and orchestration layer for learning: it retrieves stable concepts and grounded source context from upstream KG/vector services, automatically chooses what should be studied using FSRS, mastery, coverage, exam timing, and available time, generates and validates learning material, runs flashcard, quiz, Feynman, and challenger sessions, and exclusively owns the resulting learning state in `<AI Code>/Database/SQLite/study_system/study_system.db`. Ingestion, raw-data management, concept deduplication, taxonomy enforcement, KG construction, and vectorization remain separate upstream responsibilities. The normal experience is one action — **Study now** — while the same capability layer remains callable through buttons, CLI commands, and future MCP tools. Phone synchronization is added only through a versioned, validated, idempotent exchange sandbox.

[YOUR COMMENT: Final wording or overall correction.]
