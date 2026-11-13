# Assignment 7: an agent that answers from what it has indexed

The Session 6 agent with a vector memory added. It can index documents,
find passages by meaning and not only by matching words, and keep that index
between runs. On top of it sits a small application: a reference library of
finance and reasoning topics that the agent answers from.

## What changed from Session 6

**Memory** (`memory.py`) now stores an embedding (a list of numbers that
captures the meaning of a text) with every fact. A read tries the vector index
first and falls back to keyword overlap when that finds nothing.

**The index** (`vector_index.py`) is a FAISS index saved in `state/`, so a new
process picks up where the last one stopped. If the index file is lost it is
rebuilt from `state/memory.json`.

**Two new tools** in `mcp_server.py`: `index_document` cuts a file into
400-word chunks with an 80-word overlap and stores each one, and
`search_knowledge` returns the chunks closest in meaning to a question, each
with the file it came from.

**The gateway** (`gateway.py`) gained an `embed()` call. Everything else,
including `perception.py`, `decision.py`, `action.py` and the loop in
`agent7.py`, is the Session 6 code.

Perception's prompts name no tools. A test checks every tool name against both
prompts, which is the gate the brief asks for.

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

Put one key in `.env`. A Gemini or OpenAI key covers both chat and embeddings.

## The corpus

`corpus/topics.txt` lists the Wikipedia articles in the library, one title per
line. `corpus/manifest.csv` is the manifest: file, title, link, word count and
licence for every item.

Fetch the articles (already done; the files are in `sandbox/corpus/`):

```bash
uv run python build_corpus.py download
```

Index them (needs a key; this is what the queries below depend on):

```bash
uv run python build_corpus.py index
```

To index your own notes or highlights instead, point it at a folder of `.md`
or `.txt` files:

```bash
uv run python build_corpus.py index /path/to/your/notes
```

## The eight base queries

Start clean:

```bash
rm -rf state
```

Queries A to D are the Session 6 queries; see the commands in that
assignment. The four new ones:

```bash
uv run python agent7.py "Index the file papers/attention.md and tell me what the three key contributions of the Transformer architecture are according to this paper."
```

```bash
uv run python agent7.py "Index every .md file under papers/. Confirm how many chunks were indexed in total."
```

```bash
uv run python agent7.py "Across the papers I have indexed, what do they say about chain-of-thought reasoning?"
```

```bash
uv run python agent7.py "Across these papers, how do they handle the credit assignment problem?"
```

```bash
uv run python agent7.py "Compare how the ReAct paper and the Chain-of-Thought paper differ in their treatment of intermediate reasoning."
```

## With and without the corpus

To see what the agent says when it has no index, run the same question
against an empty state folder:

```bash
A07_STATE_DIR=state_empty uv run python agent7.py "your question"
```

## Tests

```bash
uv run pytest
```

The offline tests replace the embedding model with a small stand-in, so they
check the plumbing (what is stored, what comes back, what survives a restart)
without a key.

## Still to do

The eight base traces, the five custom queries against the corpus, and their
no-corpus comparison are not here yet. They need a model key to run.
