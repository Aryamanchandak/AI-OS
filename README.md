# AI OS

The plan is [`AI OS plan.html`](AI%20OS%20plan.html), a view of `plan/stages.md`.

## Where things are

| Folder | What it holds | Status |
|---|---|---|
| `plan/` | Stages, node plans, interfaces and decisions. The only source of truth for the plan. | Active |
| `gateway/` | The AI OS model gateway (interface I1). The only AI OS node built so far. | Active |
| `projects/` | Every project built before or beside the AI OS, one copy each, grouped by what it does. | Reference; pieces get pulled into AI OS nodes |
| `coursework/` | EAG V3 course lectures and assignments. | Reference |
| `docs/` | Architecture notes, capstone plans, backlog and history that span more than one project. | Reference |
| `data/` | Snapshot of the shared `Database/` folder (SQLite, Neo4j, Chroma, raw captures). No code. | Data |
| `archive/` | Superseded versions kept only to trace lineage. Nothing here is current. | Frozen |

New AI OS code (`core/`, the stage nodes) goes at the root next to `gateway/`, as `plan/` describes. It never goes in `projects/`.

## projects/

| Group | Projects |
|---|---|
| `platform/` | `shell` (React UI over the gateway API), `llm-gateway-v7` (the earlier shared gateway), `mcp-server`, `ai-agent`, `react-loop`, `advisor`, `running.sh` (starts Ollama and Neo4j) |
| `capture/` | `ingestion-pipeline` (merged-ingestion), `page-scanner`, `marginal-highlighter`, `ingestion-review-screen`, `chrome-plugin`, `notion-to-obsidian` |
| `learning/` | `learning-system`, `study-automation`, `flashcards` |
| `reasoning/` | `research-mcp`, `research-boundary`, `steelman-generator`, `decision-tracker`, `mental-models-creator` (Model Forge), `accountability-agent` (PRAXIS), `mirofish` |
| `life/` | `planner-and-reminders`, `planner-web`, `upi-agent`, `podcast-pipeline`, `prompt-plan-optimizer`, `interview-coach` |
| `work/` | `ai-analyst`, `financial-shenanigan`, `podcast-agent`, `audio-to-text`, `newsletter`, `book-to-skill` |
| `experiments/` | `gesture-control`, `painting-shapes`, `prefab-ui` |

`docs/architecture/AI_OS_PORTFOLIO_OVERVIEW.md` describes each project. It uses the old folder names.

## coursework/eag-v3/

Lectures 3, 4, 7, 11, 12, assignments 5, 8, 9, 10, 13, 15, and `multi-channel`. The gateway generations live here, one per folder: `lecture-11` (glc v1), `lecture-12` (glc v2), `assignment-13` (glc v3), `assignment-15` (glc v4). They share many files on purpose, since each is a full snapshot of that week.

## docs/

| Folder | What it holds |
|---|---|
| `architecture/` | The Constitution, the portfolio overview, the priority ranking |
| `capstone/` | Capstone handoff, project plans, system architecture, pitch deck |
| `backlog/` | To-do plans for the gateway, ingestion pipeline, AI agent and unified UI |
| `gateway-history/` | Design notes for the pre-AI-OS gateway and the GLC migration baseline |
| `ingestion/` | Ingestion 2 decision register, Graphiti plans, deletion inventory |
| `agent-workflow-design/` | The agent workflow design series |

## What the 12 Nov 2026 cleanup changed

The repo went from 8,416 files to 4,345. Of the removed files, 155 held content that no longer exists anywhere in the tree; all of them were older variants of a file that was kept. The rest were byte-identical copies.

- `Original Code/AI Code`, `Old Code/AI Agent`, `AI Code/Database`, `Ingestion 2/merged-ingestion` and both `Page Scanner copy` folders were copies of folders that were kept.
- Older versions were dropped where a later version of the same project exists: `AI Code/AI OS` (now `gateway/` and `projects/platform/shell`), `AI Analyst POC`, `Podcast_Agent_Ver_1` and `Ver_1 finished`, the course's `Lecture 7`, `glc_v2_fixed`, `glc_V2_original`, `glc_v2_part2` and `veritas copy`, `interview-coach.zip`, `PROJECT_PLAN_CONSOLIDATED 2.MD` and the v1 pitch deck.
- Build output and tool leftovers were removed: `gateway copy/build/`, `.DS_Store` captures, a lock file, a `tsbuildinfo` file and `sqlite/glc_install_token`.

Anything removed can be read back from the commit before the cleanup:

```bash
git show 1bb2db1:"AI Code/Work /AI Analyst POC/agent/agent7.py"
```

Paths inside project code and older docs were not rewritten, so references between projects (for example `../llm_gateway`) still use the old layout. Paths in `plan/`, `gateway/docs/` and the plan page were updated.
