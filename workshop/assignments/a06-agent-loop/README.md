# Assignment 6: a four-layer agent

An agent that splits a request into goals, works through them with tools, and
remembers facts between runs. No agent framework: the loop and the contracts
are written here.

## How it works

Each round of the loop in `agent6.py` does four things in order.

**Memory** (`memory.py`) is asked what it already knows about the query. It
keeps facts, preferences and tool outcomes in `state/memory.json`, so they
survive between runs.

**Perception** (`perception.py`) plans: it turns the query into a short list of
goals, and after each round reviews the results and decides whether the work is
finished or another block of goals is needed. It also chooses which stored page
(artifact) to attach to a goal.

**Decision** (`decision.py`) takes one goal and either answers it in text or
picks exactly one tool to call.

**Action** (`action.py`) runs that tool on the MCP server over stdio. Anything
larger than 4 KB goes to the artifact store (`artifacts.py`) and only a short
preview travels onward.

Every boundary between these layers is a Pydantic model from `schemas.py`.
Every model call goes through `gateway.py`, which also writes one line per call
(model, time taken, token counts, never the prompt) to `state/llm_calls.jsonl`.
The tool server (`mcp_server.py`) offers nine tools: web search, page fetch,
time, currency conversion, and five sandboxed file tools.

## Setup

```bash
uv sync
```

```bash
uv run playwright install chromium
```

```bash
cp .env.example .env
```

Then put one model key in `.env`.

## Run the four target queries

Start from a clean state (this wipes memory, artifacts and the call log):

```bash
rm -rf state sandbox
```

Query A, the artifact attach test:

```bash
uv run python agent6.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."
```

Query B, several goals with a fact carried between them:

```bash
uv run python agent6.py "Find 3 family-friendly things to do in Tokyo this weekend. Check Saturday's weather forecast there and tell me which one is most appropriate."
```

Query C, memory across two runs. Run 1:

```bash
uv run python agent6.py "My mom's birthday is 15 May 2026. Remember that and give me a calendar reminder for two weeks before and on the day."
```

Run 2, without clearing `state/`:

```bash
uv run python agent6.py "When is mom's birthday?"
```

Query D, reading several sources:

```bash
uv run python agent6.py "Search for 'Python asyncio best practices', read the top 3 results, and give me a short numbered list of the advice they agree on."
```

## Tests

Offline tests (no network, no model calls):

```bash
uv run pytest
```

Tool tests that need the internet:

```bash
uv run pytest -m network
```

The four target queries, run for real and checked against the brief's answers
and round limits (makes paid model calls):

```bash
uv run pytest -m live -s
```

## Terminal output of the four queries

Not captured yet. The outputs go here once the queries have been run from a
clean state with a real key.

## Perception and Decision prompts

The prompts are the `PLAN_SYSTEM` and `REVIEW_SYSTEM` constants in
`perception.py` and `SYSTEM` in `decision.py`. The prompt-of-prompts validation
JSON is still to be added.
