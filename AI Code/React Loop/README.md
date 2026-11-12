# ReAct Loop Agent

A **hand-built** ReAct loop. OpenAI is used purely as a text-in/text-out *reasoning
brain* — no `tools` param, no native function-calling, no Assistants/Responses
agentic loop. The model reads the tool list as text, replies with a JSON decision
as text, and **our** code parses it, runs the tool, and feeds the result back.
The loop mechanism is the deliverable.

## Run it

```bash
uv sync
uv run python run.py        # starts the web app and opens your browser
```

That's the whole thing: **http://127.0.0.1:8000**. Type a task, watch the loop
run, and click **Agent's UI ↗** in the top bar to see any UI the agent built for
you.

`OPENAI_API_KEY` is read from the shared workspace env file
(`/Users/aryamanchandak/Documents/AI Code/.env`). `DEEPGRAM_API_KEY` is only
needed for transcribing RSS/audio podcasts — YouTube uses free captions.

## How it works

The controller in `react_loop/loop.py` runs this cycle until the model emits a
final answer or a guard stops it:

1. **Render** the MCP server's tools into the system prompt as text.
2. **Ask** the brain for one decision. It must reply with exactly one JSON object:
   ```json
   {"thought": "...", "tool": "<name>", "tool_input": { ... }}
   {"thought": "...", "final_answer": "..."}
   ```
3. **Parse** that JSON ourselves (`parser.py`).
4. **Execute** the tool against the MCP server, which runs as a subprocess.
5. **Feed the result back** as an observation, and loop.

Nothing crashes the loop — every failure becomes feedback the model can recover
from:

| Failure | What happens |
|---|---|
| Malformed JSON / wrong shape | Bounded **repair** re-ask, capped by `max_repairs` |
| Valid JSON, unknown tool | Becomes an **observation**; the model self-corrects |
| Tool raises on the server | Becomes an **observation**; tool failure is normal control flow |

Guards cap iterations, detect repeated calls, and truncate oversized output
(`guards.py`). Every step is recorded in a trajectory (`trace.py`).

### The spine vs. the throwaway shell

The point of the design is that most of it survives a migration to a different
agent. The system prompt and the choice of MCP server live **only** in config —
never in the spine.

| Component | File | Status |
|---|---|---|
| Brain interface (`think(messages) -> str`) | `react_loop/brain.py` | spine |
| MCP client (`list_tools` / `call_tool`) | `react_loop/mcp_client.py` | spine |
| Tool renderer (pure fn: state → prompt) | `react_loop/tool_renderer.py` | spine |
| Action contract + parser | `react_loop/parser.py` | spine |
| Guards (cap, repeat-detect, truncation) | `react_loop/guards.py` | spine |
| Trajectory trace | `react_loop/trace.py` | spine |
| **Loop controller** (the `while` loop) | `react_loop/loop.py` | **throwaway** |
| System prompt + which server | `react_loop/config.py` | config |

### Design boundaries

The project deliberately stays smaller than a general agent framework:

- **Plain text decisions, not native tool calling.** The hand-built loop is the
  feature being demonstrated, so the provider receives and returns ordinary
  messages while this repository validates and executes every action.
- **JSON actions, not a `Thought/Action/Observation` text protocol.** A small,
  explicit schema is easier to validate, repair, test, and migrate.
- **One sequential action per turn.** Parallel execution, planning layers, and
  reflection loops are deferred until the simple loop has a demonstrated need
  for them.
- **Raw trajectories, not model-generated step summaries.** The trace remains
  faithful to execution without adding latency, cost, or another failure point.
- **Stateless agent runs.** The message list is the run's memory; durable files
  belong to MCP tools and their configured store.
- **Configuration outside the spine.** Prompts, model selection, and MCP server
  selection can change without rewriting parsing, guards, tracing, or the client.

## Layout

```
run.py            ← start here
react_loop/       ← the loop itself (brain, MCP client, parser, guards, trace)
simple_server/    ← the MCP server the loop calls; tools live in tools/
podcast_tools/    ← self-contained podcast/YouTube library
filestore.py      ← the shared local file store
frontend/static/  ← the web UI
tests/            ← 92 tests
```

`README.md` is the single maintained project document. Generated transcripts,
summaries, chats, audio, UI snapshots, logs, and demo trajectories are runtime
artifacts and are intentionally excluded from version control.

## The tools

The bundled `simple_server` is the default — no external server needed. Basics:
`calculator`, `get_current_time`, `text_stats`.

**Local-file CRUD** — files live in one flat store (`podcast_tools/data/`,
override with `CRUD_FILES_DIR`). Names are sanitised to a single filename: no
directories, no `..` traversal, so the agent can't write outside the store.

| Tool | Purpose |
|---|---|
| `file_create` | Create a **new** file (errors if it exists) |
| `file_read` | Read a file's full text |
| `file_update` | Overwrite or append (`mode="overwrite"｜"append"`) |
| `file_delete` | Delete a file |
| `file_list` | List the store as JSON |
| `file_write_json` | Write validated JSON |

**Generative UI (Prefab)** — the agent doesn't pick from a menu of fixed screens;
it **writes Prefab component code itself**, tailored to whatever it wants to show.

| Tool | Purpose |
|---|---|
| `list_ui_components` | Look up the Prefab component catalog before writing code |
| `render_ui` | Execute the agent's Prefab Python and publish it |
| `render_ui_from_json` | Same, but built from a JSON file in the store |

The result is served at **`/ui/latest`** (linked from the top bar). If the agent's
code has a bug, the Python error is returned to it as an observation and it tries
again. The code runs in-process via `exec()` — fine for a local single-user setup;
swap `_run_code()` for Prefab's Deno/Pyodide sandbox if you ever expose this.

**Internet (podcasts / YouTube)** — backed by the pure `podcast_tools/` library.

| Tool | Purpose |
|---|---|
| `podcast_list_feeds` | List curated feeds (name → RSS URL) from `feeds.txt` |
| `podcast_list_rss` | List recent RSS episodes (curated **name** or raw URL) |
| `podcast_list_youtube` | List recent videos from a YouTube channel id |
| `youtube_video_summariser` | One-shot: transcribe **and** summarize a YouTube video |
| `podcast_transcribe` | Save a transcript from captions or audio |
| `podcast_summarize` | Summarize a saved transcript |
| `podcast_ask` | Ask a RAG-backed question about a saved transcript |

Curated names: `joe_rogan`, `founders`, `dwarkesh`, `diary_of_a_ceo`,
`rest_is_politics`. Add your own in `podcast_tools/feeds.txt` (`slug = rss_url`).

**Read-only search** — two narrow discovery tools with no general page fetcher,
browser control, downloads, or model-selected HTTP requests.

| Tool | Purpose |
|---|---|
| `website_search` | Search DuckDuckGo and return only allowlisted-domain results |
| `research_search` | Search academic metadata through a fixed Semantic Scholar endpoint |

Website search fails closed until at least one domain is enabled. The primary
configuration is `WEB_SEARCH_ALLOWED_DOMAINS` in `.env`, as a comma-separated
list without `https://`, paths, ports, or wildcards. Alternatively, edit
`simple_server/allowed_websites.txt` and add one domain per line. An entry such
as `example.com` also allows its subdomains. Search returns titles, links, and
snippets; it does not connect to the result websites. Set
`WEB_SEARCH_ALLOWED_DOMAINS_FILE` to keep the file allowlist elsewhere. The env
list takes precedence when configured. Restart the app after changing `.env`.

**To add a tool:** drop a module in `simple_server/tools/` and decorate a function.
The docstring becomes the description, the type hints become the schema, and the
package auto-imports it. That's the whole integration.

```python
from ..app import mcp

@mcp.tool()
def greet(name: str) -> str:
    """Return a friendly greeting for the given name."""
    return f"Hello, {name}!"
```

## End-to-end demo: forcing all three tool families

This is the prompt that forces the agent through internet search, local-file
CRUD, and a Prefab UI in one run — it can't reach a UI without first saving
data, and it can't render that UI without actually reading what it saved
(`render_ui_from_json` hard-fails if the generated code ignores `data`, see
`simple_server/tools/generative_ui.py`):

```bash
uv run python -m react_loop --log-level DEBUG --log-file demo.log run --json "\
Find who owns Tata Sons by searching the web, save the key ownership facts as \
JSON to a file named tata_sons.json, then build a dashboard UI from that saved \
JSON file to show me the ownership details."
```

Expected chain: `website_search` / `research_search` (internet) → `file_write_json`
(CRUD) → `render_ui_from_json` (Prefab UI, served at `/ui/latest`). `demo.log` and
the `--json` trajectory are what to capture for the submission recording.

A second, richer variant swaps the internet leg for the podcast pipeline and asks
for an actual diagram instead of prose:

```bash
uv run python -m react_loop --log-level DEBUG --log-file demo_podcast.log run --json "\
Pick a podcast from the curated feed list (prefer a short recent episode, e.g. \
from Planet Money or Hidden Brain), find its most recent episode, transcribe it, \
and summarize it. From the summary, extract the top 5 talking points as a list of \
short insight strings and save them as JSON to a file named podcast_insights.json \
(fields: podcast_title, episode_title, talking_points as a list of 5 short \
strings). Then build a Prefab dashboard from that JSON file: show the podcast and \
episode title, list the 5 talking points, and include a Mermaid diagram that \
visually connects the 5 talking points to show how the insights relate to each \
other."
```

Expected chain: `podcast_list_feeds` → `podcast_list_rss` → `podcast_transcribe` →
`podcast_summarize` (internet + local audio/caption fetch) → `file_write_json`
(CRUD) → `render_ui_from_json` with a real `Mermaid` diagram (Prefab UI). Verified
live: the agent self-corrected twice (a bad import, then a UI draft that ignored
the saved JSON) before landing on a dashboard with the podcast title, episode
title, all 5 talking points, and a Mermaid graph relating them.

## The CLI (optional)

The web app is the front door, but every phase is drivable from the terminal:

```bash
uv run python -m react_loop brain                  # confirm the brain returns text
uv run python -m react_loop tools                  # list the server's tools
uv run python -m react_loop call calculator expression="12.5/100 * 4800"
uv run python -m react_loop run "What is 7 factorial divided by 100?"
uv run python -m react_loop run --json "..."       # machine-readable trajectory
uv run python -m react_loop web                    # same app as run.py, no browser
```

Raise verbosity with `--log-level DEBUG` (adds thoughts, args, timings) and tee to
a file with `--log-file run.log`.

### Offline demo (no API key)

```bash
uv run python examples/demo_offline.py
```

Drives the **real** MCP client, parser, guards, trace, and controller against a
tiny stub server with a scripted `FakeBrain`. Exercises the repair path and a
two-tool chain, and writes the ignored artifact `examples/sample_trajectory.txt`.

## Config (`.env`)

| Var | Default | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | — | required for live runs, summaries, podcast chat |
| `DEEPGRAM_API_KEY` | — | required for RSS/audio transcription only |
| `REACT_LOOP_MODEL` | `gpt-4o-mini` | any chat-completions model |
| `MCP_SERVER_COMMAND` / `_ARGS` / `_CWD` | bundled `simple_server` | which server to point at |
| `REACT_LOOP_MAX_ITERATIONS` | `30` | hard stop against infinite loops |
| `REACT_LOOP_MAX_REPAIRS` | `3` | bound on JSON-repair re-asks |
| `REACT_LOOP_OBS_CHAR_LIMIT` | `4000` | truncate oversized tool output |
| `REACT_LOOP_LOG_LEVEL` | `INFO` | `DEBUG` adds thoughts/args/timings |
| `REACT_LOOP_LOG_FILE` | — | also write logs to this file |
| `CRUD_FILES_DIR` | `podcast_tools/data` | where the file tools read/write |
| `APP_BASE_URL` | `http://127.0.0.1:8000` | base URL the agent hands back for UIs |
| `PODCAST_FEEDS_FILE` | `podcast_tools/feeds.txt` | override the curated feed list |
| `WEB_SEARCH_ALLOWED_DOMAINS` | — | comma-separated website-search allowlist |
| `WEB_SEARCH_ALLOWED_DOMAINS_FILE` | `simple_server/allowed_websites.txt` | website-search domain allowlist |
| `SEMANTIC_SCHOLAR_API_KEY` | — | optional higher research-search rate limits |
| `PREFAB_BUNDLED_RENDERER` | `1` (set by `generative_ui.py`) | inlines the Prefab renderer into every generated-UI snapshot instead of loading it from jsDelivr on each iframe load; unset or override with `PREFAB_RENDERER_URL` to point at a local Prefab dev server |

The loop is server-agnostic — point `MCP_SERVER_*` at any stdio MCP server and
the loop code doesn't change.

## Status

- **Verified live end to end.** With a real key, `python -m react_loop run` drives
  `gpt-4o-mini` through the hand-built loop: the model emits decision-JSON, the
  loop executes real tool calls in sequence, feeds observations back, and produces
  a final answer — no native tool-calling anywhere.
- **`uv run pytest` — 92 tests passing.** Covers the parser, guards, the whole loop
  end to end with scripted decisions (2-tool chain, repair path + exhaustion,
  unknown-tool observation, repeat guard, tool-error-as-observation, iteration cap),
  file CRUD, the generative UI, and the bundled server's discovery + execution.
- **`uv run python scripts/verify_react_loop.py`** is a live runtime harness for the
  web app + UI + store plumbing.
