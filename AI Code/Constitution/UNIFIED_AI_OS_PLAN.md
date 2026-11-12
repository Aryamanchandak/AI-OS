yes # Unifying the AI OS — the substrate under all of it, and how to link it together

*A plan, not a change. Nothing in any project has been modified. This document extends
`COMBINED_ARCHITECTURE.md` (which covered only podcast-brief + Research_MCP + study system) to the
**whole workbench** — every project except `Painting_shapes`.*

**Author:** analysis pass, 2026-06-14
**Scope:** Planner, UPI Agent, Research_MCP, podcast-brief, study system (KG + Vec DB), Sharpen (Chrome
plugin), prompt-plan-optimizer, Notion→Obsidian, Persistent Memory Chats Storage, and the loose
root files (`app.py`, `app_1.py`, `static/`).
**Explicitly out of scope:** `Painting_shapes` — see §7.
**Chosen target (your call):** shared installable packages, repos kept separate. Not a monorepo merge.

---

## 1. The headline finding

You already suspected this and you're right: **these are not ten unrelated tools. They are one
personal AI operating system that was built outward as separate rooms, and every room is standing on
the same four foundations — each room just poured its own concrete.**

The four foundations (the "substrate") are:

1. **A knowledge + memory layer that is really the Obsidian vault + markdown-as-memory.**
2. **An LLM gateway** — every room calls a model; only two rooms meter it; nobody shares one.
3. **A local store layer** — SQLite everywhere, plus ChromaDB + a NetworkX knowledge graph in one room.
4. **macOS context + agentic tool-calling** — Apple Calendar/Reminders, the read-vs-write-confirm
   loop, and MCP servers.

The previous doc proved this for three projects by quoting their own specs back at them. This pass
confirms the *same substrate runs under the other seven* — and that each one re-implements the
foundation independently, at a different level of polish, sometimes with a bug or a leaked key.

> So the integration question is not "can these be connected?" It is "which single best
> implementation of each foundation do we promote to a shared package, and which six near-duplicates
> do we retire?"

---

## 2. Every room, as it actually is today

| Room | Job | LLM | Memory / store | macOS / protocol | Real state |
|---|---|---|---|---|---|
| **Planner** | chat → Apple Calendar/Reminders, with confirm-before-write | OpenAI gpt-4o + gpt-4o-mini, **bare SDK, no meter** | session memory as **markdown in the Obsidian vault** (`Agent MD/`) | AppleScript via NSTask; agentic read/write loop | Working V2; the most "central" room |
| **UPI Agent** | UPI SMS → categorised local ledger + dashboard | optional OpenAI narrator, no meter | local **SQLite** ledger `~/.upi-agent/data.db` | reads Apple Calendar (osascript) for enrichment | Consolidated to `core/`; 74 tests |
| **Research_MCP** | topic → multi-source cited essay; claim verification | Anthropic, **`MeteredClient` (the good meter)** | **SQLite** source store + JSONL audit | **FastMCP** server + internal Python client | Phase 1 done, tests green; judgment deferred |
| **podcast-brief** | podcast URL → transcript → claims → research → brief → Readwise | Anthropic Sonnet/Opus + Deepgram, **no meter** | in-flight state only | CLI | V2; V3 (agents/aggregator) ~0% built |
| **study system** | Obsidian notes → concepts/KG → flashcards → FSRS review | OpenAI + Anthropic via **`LLMClients` gateway** (spend log, **buggy cost row**) | **SQLite + ChromaDB (vector) + NetworkX (KG)** | CLI | Phases 1–2 partial; owns the KG/vector stores |
| **Sharpen** (Chrome) | counterarguments / bias / debate on any page | OpenAI gpt-4o-mini + gpt-5, **raw fetch, key in client** | `chrome.storage` | browser side panel | Working; **leaks an API key** |
| **Optimizer** | split a prompt/plan into sections, chat-edit each, diff, conflict-check | Anthropic Sonnet (`claude.ts`), no meter | `localStorage` versioning | Next.js + server relay | Backend logic written; UI is a placeholder |
| **Notion→Obsidian** | migrate Notion pages into the vault | — | writes **markdown into the Obsidian vault** (`Notion/`) | one-off script | Works; **leaks a Notion key** |
| **Persistent Memory Chats Storage** | per-agent markdown memory for Claude Code agents | — (consumed by agents) | **markdown-as-memory** under `AI OS/…/Agent Memory/` | typed `<type>__<slug>.md` + `MEMORY.md` index | Convention in active use |
| **root `app.py` / `app_1.py` / `static/`** | top-level FastAPI entry that re-hosts the Planner and tries to mount UPI | (delegates to Planner) | — | FastAPI | **Stale**: imports `from brain.dashboard` but UPI moved to `core/`; two near-identical copies (drift) |

---

## 3. The substrate, made explicit

This is the part that was never written down in one place. Each row is one foundation, who does it
best today, and who is duplicating or breaking it.

### 3.1 Knowledge + memory layer — the Obsidian vault is already the shared brain, just fragmented

Three rooms already read or write **the same Obsidian vault**, and a fourth uses the identical
markdown-as-memory idea in a different folder:

- Planner writes session memory to `…/Aryamans Vault/Agent MD/` (dated `.md`, carry-forward notes).
- Notion→Obsidian writes pages to `…/Aryamans Vault/Notion/`.
- study system *reads* Obsidian notes as its ingestion source.
- Persistent Memory Chats Storage uses `<type>__<slug>.md` + a `MEMORY.md` index — but under
  `~/Documents/AI OS/…/Agent Memory/`, **outside the vault**.

**The fault:** there are at least three memory roots, all **hardcoded absolute paths**, no env var, no
shared accessor, and **no shared entity namespace** — an entity named in a Planner session cannot
resolve to the same node as the same entity in a study concept or a Notion page. The payoff of a
unified brain (cross-references) is something the current code *cannot express*. This is the same
fault line §4.2 of the prior doc raised — it just turns out to span five rooms, not three.

### 3.2 LLM gateway — six implementations, two meters, one wrong number, one leaked key

| Room | Provider(s) | Metered? | Notes |
|---|---|---|---|
| Research_MCP | Anthropic | **Yes — `MeteredClient`, dated pricing, JSONL+SQLite** | the reference implementation |
| study system | OpenAI + Anthropic | partial — `LLMClients` logs spend | **cost table has `claude-sonnet-4-5`; config uses `claude-sonnet-4-6`** → extraction billed at gpt-4o fallback rate |
| Planner | OpenAI | no | bare `OpenAI()` |
| podcast-brief | Anthropic + Deepgram | no | bare SDK |
| Optimizer | Anthropic | no | `claude.ts` |
| Sharpen | OpenAI | no | **API key hardcoded in client-side JS** (§6) |

Two rooms independently built "the one gateway every module calls" (Research_MCP's `MeteredClient`,
study's `LLMClients`). Neither is shared. There is **no global budget ceiling** across the OS — a
combined system could overspend silently in four of six rooms.

### 3.3 Store layer — SQLite is universal; one room owns the graph everyone wants

SQLite is the common denominator (UPI ledger, Research_MCP sources, study system store). The study
system additionally owns **ChromaDB (vector) + NetworkX (knowledge graph)** — which is exactly the
backend Research_MCP's Phase 2 and podcast-brief's planned `core/memory/` both name as their target.
But that backend has documented holes (retrieval returns `[]`; cross-file KG triplets dropped;
ChromaDB optional). It is a substrate-in-waiting, not a finished substrate.

### 3.4 macOS context + agentic tool-calling — duplicated calendar access, two MCP servers, one loop pattern

- **Apple Calendar** is read by **both** Planner (AppleScript/NSTask, read+write) and UPI (osascript,
  read-only enrichment) — two separate calendar accessors.
- **MCP servers**: Research_MCP (FastMCP, real) and Painting_shapes (toy). The Agent Memory store is
  explicitly built *for* Claude Code agents over MCP.
- **The read-vs-write-with-confirmation agent loop** in the Planner is a reusable control pattern no
  other room borrows.
- Shared environment law everyone restates: **no `fork()` on macOS** with the LLM SDKs loaded.

### 3.5 Conventions adopted to three different depths

Prompts-as-files (Research_MCP strict/versioned ▸ study files-but-unvalidated ▸ podcast/Optimizer/
Planner partly inline), typed contracts (Research_MCP frozen Pydantic ▸ study `types/` ▸ Optimizer
`types.ts` ▸ podcast `@dataclass`), and model/cost config (no single source of truth) all exist at
three maturity levels. Consolidation = pick the strict one, drag the others up.

---

## 4. Duplication matrix — what gets deleted when each foundation is shared

| Foundation | Promote the best existing… | …and retire / fix |
|---|---|---|
| **LLM gateway + meter** | Research_MCP `MeteredClient` + dated pricing, extended to multi-provider (absorb study's OpenAI path) + **one enforced global budget** | Planner bare SDK; podcast bare SDK; Optimizer `claude.ts`; Sharpen client-side key; study's buggy cost table |
| **Knowledge/memory substrate** | study `vector/` + `kg/` + `storage/` (holes fixed) **+** one `VaultClient` over the Obsidian vault | Planner's hardcoded `Agent MD/` path; Persistent-Memory's separate root; podcast's planned-but-unbuilt `core/memory/` — unified under one entity namespace |
| **Research engine** | Research_MCP, kept standalone (MCP + Python client) | podcast's hardcoded `research/` mix; any future ad-hoc research in study |
| **Calendar/macOS context** | Planner's AppleScript/NSTask layer, extracted as a package | UPI's separate osascript calendar reader |
| **Contracts / identity** | Research_MCP frozen Pydantic, extended with a unified `Entity / Claim / Source / Note` | podcast `@dataclass`; isolated study/Optimizer types |
| **Prompts-as-files** | Research_MCP's strict versioned convention | study's unvalidated vars; inline prompts in Planner/podcast/Optimizer |

Each shared layer **deletes a triplicated, partly-broken implementation** and gives cross-references a
place to live.

---

## 5. Target architecture — shared packages, repos kept separate (your chosen shape)

The point is **horizontal capabilities consumed by vertical apps**, *not* folding one app inside
another. Keep each repo standalone; extract the foundations into installable packages
(`aios-gateway`, `aios-memory`, `aios-contracts`, `aios-macos`) that every app depends on. This
preserves Research_MCP's "standalone + absorbable" property and Sharpen's separateness, while killing
the duplication.

```
 VERTICAL APPS  (each a standalone repo; consumes shared packages)
 ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐
 │ Planner │ │   UPI    │ │ podcast- │ │  study   │ │ Sharpen  │ │ Optimizer │
 │ cal/rem │ │  ledger  │ │  brief   │ │  cards   │ │ (browser)│ │ prompt/dx │
 └────┬────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬─────┘
      │           │            │            │            │             │
      │  (Sharpen & Optimizer reach shared layers through a thin local HTTP/MCP gateway,
      │           │     since they're JS/TS, not Python)                │
      ▼           ▼            ▼            ▼            ▼             ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  RESEARCH / AGGREGATOR SERVICE   (Research_MCP, standalone: MCP + client)  │
 │  triage → expand → fetch → dedup → annotate → synthesize → citation-gate   │
 └───────────────┬───────────────────────────────────────┬──────────────────┘
                 │ writes provenanced essays/sources       │ reads/writes
                 ▼                                         ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  aios-memory  — SHARED KNOWLEDGE + MEMORY SUBSTRATE                        │
 │  Obsidian VaultClient  +  SQLite  +  ChromaDB (vector)  +  NetworkX (KG)   │
 │  one Entity namespace · MemoryClient(search_entities/claims/sources/notes) │
 │  (promoted from study/store + the markdown-memory convention; holes fixed) │
 └───────────────┬───────────────────────────────────────┬──────────────────┘
                 ▼                                         ▼
 ┌──────────────────────────────┐   ┌───────────────────────────────────────┐
 │ aios-gateway — LLM + METER    │   │ aios-contracts — Entity/Claim/Source/  │
 │ multi-provider, dated pricing │   │ Note + prompts-as-files convention     │
 │ ONE global budget ceiling     │   └───────────────────────────────────────┘
 └──────────────────────────────┘   ┌───────────────────────────────────────┐
 ┌──────────────────────────────┐   │ aios-macos — Apple Calendar/Reminders  │
 │ MCP SURFACE (FastMCP)         │   │ (NSTask) + the confirm-before-write    │
 │ research + memory + calendar  │   │ agent-loop pattern                     │
 │ exposed to Claude Code agents │   └───────────────────────────────────────┘
 └──────────────────────────────┘
```

**Why this shape:** the JS/TS apps (Sharpen, Optimizer) can't import Python packages, so they consume
the same foundations through the **MCP surface / a thin local HTTP gateway** — which is the natural
way to give the browser extension metering and shared memory without leaking a key into client code.

---

## 6. Security — code leaks fixed; key rotation still owed

> **Status update, 2026-07-11 (verified this pass).** Both hardcoded-secret leaks below have been
> **remediated in source.** What remains is **rotation** — a code fix does not un-expose a key that
> was already handed out.

**Code fixes — done:**

1. **`Notion to Obsidian/Notion_to_obsidian.py`** — no longer hardcodes the token. Now
   `load_dotenv(... / ".env")` + `os.environ["NOTION_API_KEY"]`. ✅
2. **`Chrome Plugin/sidepanel.js`** — no longer ships an OpenAI key. Client calls now proxy through a
   local relay `server.py` (`${serverUrl}/openai/chat`); the key is read server-side from `.env` and
   set in the `Authorization` header. This is exactly the local-relay pattern §5 prescribes. ✅

**Hygiene verified this pass:** no key strings anywhere in source; no `.env` tracked by git; no key in
any git history blob (all 5 repos checked); no git remotes on any repo; the two `.env` files that live
inside git repos are both `.gitignore`d.

**Still owed — ROTATE BOTH KEYS (open action):**

- **OpenAI key** (formerly in `Chrome Plugin/sidepanel.js`). A client-side extension key is visible to
  anyone who ever loaded, packed, or inspected that build. If the old version left this machine in any
  form, **treat as compromised and rotate in the OpenAI dashboard**, then confirm only the `.env` copy
  remains.
- **Notion integration token** (formerly `ntn_…` in `Notion_to_obsidian.py`). **Rotate in Notion**,
  then confirm only the `.env` copy remains.
- After rotating, grep the workspace for the old key values to confirm no stale reference survives in
  logs (`llm_logs.md`, `gateway.log`), notes, or scratch files.

These are external dashboard actions (cannot be automated from the repo) and are the last remaining
security item before integration work.

---

## 7. Why Painting_shapes is correctly excluded

`Painting_shapes` is a pyautogui/MCP experiment that takes screen corner coordinates and draws a
circle/square/rectangle with text. It is the one project that touches **none** of the four
foundations: no knowledge/memory layer, no LLM reasoning over your data, no shared store, no calendar
or vault. Its only overlap with the others is the literal word "MCP." It belongs on the workbench as a
toy, not in the OS substrate. Leave it standalone.

---

## 8. Sequenced plan (risk-ordered; honest about what's shovel-ready)

> Reality check: only Phase 0 and Phase 1 are low-risk. Everything after is net-new construction or
> requires fixing known holes first. The clean diagram in §5 hides that most of this is building, not
> wiring.

**Phase 0 — Secrets + `aios-gateway` + `aios-contracts`.** *Lowest risk, immediate payoff.*
Rotate both keys (§6). Stand up `aios-gateway` from Research_MCP's `MeteredClient`: extend to OpenAI
(study + Planner + Sharpen + podcast need it), fix study's cost-row bug, add an enforced global budget
ceiling. Define `aios-contracts`: a unified `Entity / Claim / Source / Note` that the other type
worlds map onto, plus the strict prompts-as-files convention.

**Phase 1 — Two shovel-ready wirings.**
(a) **podcast-brief → Research_MCP**: replace podcast's hardcoded `research/` mix with a call to
Research_MCP's Python client — this is literally Research_MCP's own Phase 1.4 exit criterion (mind the
sync↔async boundary). (b) **Fix the root entry**: `app.py`/`app_1.py` import `from brain.dashboard`
but UPI now lives in `core/` — repoint the `/upi` mount and collapse the two drifting copies into one.

**Phase 2 — `aios-memory`: stand up the shared substrate.** Promote study's `vector/ + kg/ +
storage/` and add a `VaultClient` over the Obsidian vault behind one env-configurable root. **Fix the
holes first**: implement `retrieve_atomic_facts_for_concept`, stop dropping cross-file KG triplets,
make ChromaDB non-optional *for the service*. Give it the `MemoryClient` API podcast's V3 already
names. Unify the three memory roots (Planner `Agent MD/`, Notion `Notion/`, Persistent-Memory
`Agent Memory/`) under it.

**Phase 3 — `aios-macos` + one entity namespace + retroactive indexing.** Extract Planner's
calendar/NSTask layer as a package; retire UPI's separate calendar reader so spend-vs-calendar
enrichment and planning read the *same* calendar code. Establish one entity namespace; index
Research_MCP's provenanced essays and the vault into the KG/vector store (free because Phase 1 kept
full provenance).

**Phase 4 — cross-domain memory over MCP.** study system and Planner call the aggregator + memory
over MCP; Sharpen and the Optimizer route their LLM calls through the gateway surface (kills the
leaked key for good). A podcast claim, a study concept, and a Planner follow-up can now resolve to the
**same node**. This is the point where it stops being ten tools and becomes an OS.

---

## 9. Open decisions for you

1. **Which control flow wins for research** (carried over from the prior doc): the two-axis
   correctness×effort engine, with `profile` demoted to a source hint? *Recommended: yes.*
2. **Does `aios-memory` make ChromaDB mandatory** for the service (forcing the holes to be fixed),
   while standalone study keeps graceful degradation? *Recommended: yes.*
3. **One Obsidian root for all memory**, or keep the Persistent-Memory agent store separate from the
   vault? *Recommended: one root, with `agent-memory/` as a subtree, so cross-references work.*
4. **How do the JS/TS apps consume the substrate** — local HTTP gateway, MCP, or both? *Recommended:
   the MCP surface, reusing Research_MCP's server, with a thin HTTP shim for the browser.*
5. **How rigorous does study-card grounding become** — route card generation through the same citation
   gate over time? *Recommended: yes, but don't block Phases 0–2 on it.*

---

## Appendix — traceability (every claim above maps to a file read this pass)

- **overview**: `overview/overview.md` (ten-project map), `COMBINED_ARCHITECTURE.md` (3-project deep dive).
- **Planner**: `…/memory.py` (`MEMORY_DIR = …/Aryamans Vault/Agent MD`, gpt-4o-mini, injection
  sanitiser), `…/planner.py` (bare `OpenAI()`, gpt-4o, read/write agent loop), `CLAUDE.md`/
  `guiding_principles.md` (three modes), `Technical MD/memory.md` (hardcoded-path risks).
- **UPI**: `README.md`, `CLAUDE.md`, `CONSOLIDATION_PLAN.md` (SQLite ledger, `core/`, calendar
  enrichment via osascript).
- **Research_MCP**: prior doc's citations + confirmed `MeteredClient` as the reference meter.
- **podcast-brief**: `core/pipeline.py` (Deepgram, Claude Sonnet/Opus, Readwise; no meter).
- **study system**: `core/config.py` (model split), `core/clients.md` (cost-table `4-5` vs `4-6`
  bug), `kg/kg_store.py` (NetworkX), `vector/vector_store.py` (lazy ChromaDB), `storage/`.
- **Sharpen**: `manifest.json`, `sidepanel.js:52` (hardcoded OpenAI key), gpt-4o-mini/gpt-5.
- **Optimizer**: `overview/overview.md`, `lib/claude.ts` (Sonnet, server relay), `lib/*` modules.
- **Notion→Obsidian**: `Notion_to_obsidian.py` (hardcoded Notion token; writes vault `Notion/`).
- **Persistent Memory**: `Agent Memory/README.md` (`<type>__<slug>.md` + `MEMORY.md` index).
- **root**: `app.py`/`app_1.py` (`from brain.dashboard import app` — stale vs UPI `core/`; two copies).
