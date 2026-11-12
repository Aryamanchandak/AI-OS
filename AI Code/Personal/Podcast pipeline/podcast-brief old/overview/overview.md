# Podcast Brief — Codebase Overview

**Last updated:** 2026-06-23

---

## 1. What This Project Is

Podcast Brief is a personal research assistant for audio content. You point it at a podcast episode — a YouTube link, a direct audio file, or an RSS feed item — and it produces a structured, fact-checked written brief that lands in your Readwise Reader inbox. The brief is not a transcript or a summary. It is an annotated research document: the host's key claims, what the academic literature or news record actually says about each one, and guidance on what is worth your full attention. The system is designed for a single person's private use, processing one episode at a time.

---

## 2. The Big Picture — How It All Fits Together

Think of the system as a six-room factory that an audio file walks through from start to finish. Each room does one job, leaves its work on a shelf, and the next room picks it up from there. No room holds the door open for another; everything is handed off through files on disk.

The factory has three ways in: a command-line terminal you type into, an HTTP server you can send requests to from your phone via an iOS Shortcut, and an MCP server that lets Claude Desktop or another AI client drive the pipeline tool by tool. All three doors lead to the same factory floor.

The six rooms in order are:

**Ingestion** downloads the audio file. It uses YouTube's unofficial download tools for YouTube and podcast hosting platforms, or a direct HTTP download for plain MP3 links. It deduplicates: if you've already processed this episode, it skips the download.

**Transcription** sends the audio to Deepgram's speech-to-text service, which returns a diarized transcript — meaning it labels who was speaking at each moment, as "Speaker 0," "Speaker 1," and so on. A small, cheap AI call then resolves those generic labels into real names like "Lex" and "Guest."

**Extraction** reads the transcript and pulls out the ten to twenty most research-worthy claims made in the episode. The type of claims it looks for depends on the show's profile: a science podcast gets references to papers and statistical claims; a political show gets factual assertions and historical claims; a business biography show gets a mix of both.

**Research** takes each extracted claim and checks it against external sources. It delegates this work to a separately installed package called Research_MCP, which handles the mechanics of querying Semantic Scholar, arXiv, Wikipedia, Brave Search, and similar resources. The result for each claim is a verdict (true, false, or neither) plus a set of supporting or contradicting sources.

**Synthesis** is where everything comes together. Claude — the most capable and expensive AI model the system uses — reads the transcript, the extracted claims, and the research findings, and writes the final brief as a markdown document. The exact structure of the brief (its sections, tone, and emphasis) is controlled by a profile-specific template.

**Delivery** converts the markdown brief to HTML and pushes it to your Readwise Reader inbox via their API, where it appears alongside your other saved reading.

Underneath all of this, a SQLite database acts as a running logbook. It remembers every episode that has been processed, prevents the same episode from being processed twice, and records the outcome of each stage so you can audit what happened.

The three configuration files that shape the whole system are: `shows.yaml` (which shows exist and what their profiles are), the three prompt template files in `config/prompts/` (which control how each type of brief is written), and the `.env` file (which holds API credentials).

---

## 3. Every Component — What It Does and Why It Exists

### The Core — The Pipeline Engine

**The Orchestrator** (`core/orchestrator.py`) is the central nervous system. It contains a single function that runs all six stages in fixed order. It handles the two shortcut modes — `transcript_only` (stop after delivery of the raw transcript, skipping extraction through synthesis) and `skip_research` (skip the research stage but still extract and synthesize). After each stage it writes a status record to SQLite. If the research stage fails, it warns and continues to synthesis without research results rather than aborting entirely. All status messages go to the standard error stream rather than standard output, which keeps the MCP protocol's stdio channel clean.

**The Stage Functions** (`core/stages.py`) are the actual building blocks. Each of the six stages is a function here. Every function follows the same contract: accept an episode ID, load its inputs from the appropriate disk location, do its work, write its outputs to disk, and return a structured result object. This design means each stage can be called independently — by the orchestrator for a full run, or by an MCP tool for step-by-step control. The stages are stateless in the sense that none of them hold results in memory between calls; disk is the shared memory.

**The Pipeline Compatibility Wrapper** (`core/pipeline.py`) is a one-function shim that lets the CLI and HTTP server call `run_pipeline()` without needing to know that the underlying implementation lives in `orchestrator.py`. It exists purely to avoid breaking callers when the internals were reorganized.

**The Data Models** (`core/models.py`) define every data structure the system uses, from the raw audio download result all the way to the final delivery confirmation. The most important model is `Transcript`, which also knows how to shrink itself to fit within the AI's context window: it keeps the first 60% and last 20% of the content and drops the middle if the episode is very long. These Pydantic models act as contracts between stages: a stage's output type is the next stage's input type.

**The Configuration System** (`core/config.py`) is the single source of truth for everything that can be configured: which AI model to use at each stage, where on disk to store audio files, transcripts, briefs, and research results, and how to read the show definitions and prompt templates. The three AI models used are: a Haiku-class model for cheap throwaway tasks like speaker name resolution, a Sonnet-class model for structured work like claim extraction, and an Opus-class model for the final synthesis where quality matters most.

**The State Database** (`core/state.py`) manages the SQLite logbook. It maintains two tables: one for episodes (each row is one podcast episode, with its paths, profile, status, and final Reader URL) and one for stage runs (each row is one execution of one stage, with its status and any error message). This is how the system avoids re-processing, how the MCP verification gate works, and how the `recent` command shows history.

**The LLM Gateway** (`core/llm.py`) is the single function all AI calls flow through. It wraps the Anthropic SDK with automatic retry logic: if the API returns a rate-limit error or server error, it waits and tries again, up to five times, with waiting periods that grow from four seconds to sixty seconds. This means transient API problems are invisible to the rest of the system.

### The Ingestion Layer

**Audio Fetching** (`ingestion/ingest.py`) handles the download. For YouTube URLs and podcast hosting platforms, it uses yt-dlp, a mature open-source tool. For direct MP3 links, it uses a plain HTTP download. Deduplication happens by episode ID: YouTube episodes use the video's ID as their key; everything else uses a hash of the URL. If that ID already has a local audio file, the download is skipped. This module also provides two functions for polling: one that reads new episodes from an RSS feed, and one that checks a YouTube channel.

**Polling** (`ingestion/poll.py`) runs through all active shows, finds episodes that have not yet been processed by checking the SQLite state database, and runs the pipeline on each new one. It is designed to be called on a schedule — by a cron job or launchd timer — and has a dry-run mode that reports what it would do without doing it.

### The Transcription Layer

**Transcription** (`transcription/transcribe.py`) sends the audio to Deepgram's Nova-3 model with speaker diarization turned on. Diarization means Deepgram listens for who is speaking and segments the transcript accordingly. The raw result from Deepgram uses anonymous labels. A second step then asks the Haiku-class AI to look at the first thirty segments and any speaker hint provided at run time, and map the anonymous labels to real names. Results are cached: if a transcript already exists on disk, the Deepgram call is skipped.

### The Extraction Layer

**Claim Extraction** (`extraction/extract.py`) sends the transcript to the Sonnet-class AI with a prompt asking it to find ten to twenty research-worthy claims. The prompt specifies which claim types are relevant for the show's profile. Every claim in the result carries: its type, the speaker who made it, the timestamp in the audio, a verbatim quote, a short summary, and a suggested search query for the research stage.

### The Research Layer

**The Research Bridge** (`research/mcp_bridge.py`) is how the system delegates all research work to the external Research_MCP package. It calls Research_MCP's engine function, which handles all the querying of academic databases and web sources. Because Research_MCP uses async code internally and the rest of this pipeline is synchronous, the bridge runs the async work in a thread pool to keep the two models from conflicting. The results come back as source objects, which the bridge converts into the local `LogicalSource` format and saves to disk.

**The Three Superseded Crawlers** (`research/academic.py`, `research/news.py`, `research/books.py`) are dead code from an earlier version of the system (V2) that did its own research by directly querying Semantic Scholar, arXiv, Brave Search, and Google Books. These three files have no callers anywhere in the current codebase. They exist on disk but play no role in any execution path. They should be treated as historical artifacts.

### The Synthesis and Delivery Layer

**Synthesis** (`summarisation/synthesize.py`) builds the final brief. It assembles a prompt that includes the full transcript, the list of extracted claims, and the research findings formatted as a readable block. This prompt goes to the Opus-class AI with a profile-specific system message drawn from one of the three template files in `config/prompts/`. The AI returns up to eight thousand tokens of structured markdown.

**Formatting** (`summarisation/format.py`) converts markdown to HTML for Reader delivery. It uses a Python markdown library with several extensions for features like tables and smart punctuation. There is also a function that converts a raw transcript into readable HTML, grouping consecutive segments from the same speaker into paragraphs with timestamps.

**Delivery** (`delivery/deliver.py`) pushes the HTML to Readwise Reader's API. The Reader API responds with a URL that permanently links to the saved document. That URL is stored back in the SQLite episode record. There is also a token verification function used by the `check` CLI command to confirm the Readwise credentials are valid.

### The Interface Layer

**The CLI** (`interface/cli.py`) provides five commands: `brief` (process a single URL), `poll` (check all shows for new episodes), `recent` (show history), `check` (verify API keys and connectivity), and `browse` (interactively pick an episode from a show's RSS feed in the terminal). All five commands eventually call into the pipeline or the state database.

**The MCP Server** (`interface/mcp_server.py`) exposes the same pipeline as tools for any MCP-compatible client, most practically Claude Desktop. It registers a `generate_brief` tool that runs the complete pipeline in one call, plus individual tools for each stage — letting an AI client pause between stages to inspect intermediate results. It also registers four admin tools and a resource endpoint that lets you read a completed brief as text without re-running anything. The MCP server runs via streamable HTTP when mounted inside the FastAPI server, or via stdio when launched as a standalone process.

**The HTTP Server** (`interface/server.py`) combines both surfaces into one process. It is a FastAPI application that mounts the MCP server at `/mcp` and exposes three HTTP endpoints of its own: a health check at `/`, a `POST /brief` endpoint for the iOS Shortcut integration, and a `GET /recent` endpoint for history. The brief endpoint returns immediately with a "queued" response and runs the pipeline in a background thread — so the Shortcut doesn't have to wait through the several minutes the pipeline takes. Optional token authentication is available via an environment variable.

### Configuration Files

The `config/` directory contains five things: `shows.yaml` (three pre-configured shows: Lex Fridman as academic, Founders as hybrid, Ezra Klein as current events), `trusted_sources.yaml` (a whitelist of news sources used internally by the superseded V2 crawlers — no longer used by the active research path), and three prompt template files that define the structure of the brief for each profile. The `agent_playbook.md` file in that directory is not a configuration file but an instruction document for AI clients using the MCP server.

### Peripheral and Standalone

**The Index Script** (`scripts/index_transcript.py`) is a standalone utility that bridges this project to the broader AI OS workspace. It takes a podcast URL, transcribes it through this pipeline's transcription stage, then forwards the transcript into three other systems: a markdown archive, a ChromaDB vector store (for semantic search over podcast content), and a SQLite knowledge graph (where Claude Opus extracts concepts and relationships). This script is not part of the main brief pipeline; it runs independently and requires the separate `study_system`, `knowledge_graph`, and `vector_db` packages from the parent workspace to be installed.

---

## 4. How a Typical Interaction Works

The most common path is a user sharing a podcast link from their phone. The iOS Shortcut sends the URL to `POST /brief` on the FastAPI server running on their laptop. The server matches the URL against the configured shows — if it recognizes the domain, it applies that show's profile automatically; otherwise it defaults to "hybrid." The server responds immediately with "queued" so the Shortcut doesn't time out, and starts the pipeline in a background thread.

The pipeline begins by generating an episode ID from the URL and checking whether this episode has already been processed. If it has, the run ends early. If not, it creates a new episode record in SQLite and begins stage one.

The audio is downloaded — typically two to four hours of content in MP3 format — and saved to a local directory. With the audio on disk, the transcript stage sends it to Deepgram. This usually takes a few minutes. Deepgram returns a diarized transcript with speaker labels, which is saved to disk and then passed to the speaker name resolver, which makes a quick AI call to turn "Speaker 0" into "Lex" and "Speaker 1" into "Guest."

Next, the Sonnet AI reads the transcript and extracts claims. For a hybrid profile show like Founders, it might pull fifteen claims across academic references, statistics, historical claims, and predictions. Each claim goes into a JSON file on disk.

The research stage loads those claims and calls into the Research_MCP package, which queries academic databases and the web for each claim. Results come back with verdicts and source lists and are saved to disk.

Finally, the Opus AI reads everything — transcript, claims, research — and writes the brief. The brief is a markdown document structured into sections: an episode summary, each claim annotated with its research context and sources, must-listen moments, and further reading. The markdown is converted to HTML and pushed to Readwise Reader, which sends back a URL. That URL is stored in SQLite and the episode record is marked complete.

The user opens their Readwise Reader app, finds the document in their inbox, and reads the brief.

A second common path is the MCP step-by-step mode. An AI client such as Claude Desktop calls `ingest_audio`, then checks `get_episode_status` to confirm it completed, then calls `transcribe_episode`, checks status again, and so on through each stage. This mode is useful when the user wants to inspect the extracted claims before committing to the research and synthesis steps.

---

## 5. How the System Makes Decisions

**Which profile to use** is the first major decision point. If the URL matches a configured show, that show's profile is used. If not, the profile falls through to whatever was passed as a parameter, defaulting to "hybrid" if nothing was specified. The profile governs which claim types are extracted and which synthesis template is used.

**Whether to skip research** is controlled by a flag. When set, the orchestrator simply skips the research stage and writes an empty research result to disk. The synthesis stage still runs, but without any external verification data to draw from.

**Whether to use transcript-only mode** short-circuits the extraction, research, and synthesis stages entirely. The transcript is formatted and pushed to Reader as the final product.

**Whether an episode is new** is determined by looking up the episode ID in SQLite. If a row exists with any status other than error, the episode is skipped. If it errored previously, the current code creates a new record and tries again.

**How long the transcript to send to the AI** is determined by a character count. If the transcript is under 180,000 characters, it is sent in full. If it is longer — as very long episodes can be — the system keeps the first 60% and the final 20% of the content, discarding the middle. This is a heuristic: the opening is typically the most substantive discussion, and the closing often contains important conclusions.

**Which AI model handles each task** is fixed in configuration, not decided at runtime. Cheap throwaway tasks go to Haiku, structured extraction goes to Sonnet, and synthesis goes to Opus. This is a cost-and-quality optimization baked into the design.

**Whether to retry an AI call** is decided by the retry wrapper. If the Anthropic API returns a rate-limit or server error, it retries automatically. If the error is something else — a malformed request, a content policy refusal — it propagates immediately.

**Whether to abort on research failure** is the key resilience decision: the orchestrator catches research failures, logs a warning, and continues to synthesis without research data, rather than failing the entire run. Delivery failures are also caught: if the Reader push fails, the markdown brief remains on disk.

---

## 6. How the Code Actually Flows — The Execution Journey

**Entry point: CLI.** When you run `podcast-brief brief <url>` in a terminal, Python finds the `main()` function in `interface/cli.py`, which was registered as the entry point when the package was installed. The CLI parses the arguments, loads environment variables from the `.env` file, looks up the show configuration if applicable, and calls `pipeline.run_pipeline()`, which is the compatibility shim that immediately calls `orchestrator.process_episode()`.

**Entry point: HTTP.** When a POST arrives at `/brief`, FastAPI dispatches it to the handler function in `interface/server.py`. The handler validates the optional token, looks up the show, constructs a closure that calls `pipeline.run_pipeline()`, and hands that closure to FastAPI's background task runner. The response goes back to the caller immediately. The pipeline itself runs in the background without any mechanism to report back to the original HTTP caller — the result only appears in Reader.

**Entry point: MCP.** When an MCP client calls the `generate_brief` tool, the FastMCP framework invokes the registered Python function in `interface/mcp_server.py`, which calls `orchestrator.process_episode()`. When a per-stage tool is called instead, it calls the corresponding function in `core/stages.py` directly.

**The startup sequence.** All three entry points load the `.env` file immediately on import. The CLI calls `ensure_dirs()` before any command runs, creating the local data directories if they don't exist. The HTTP server's lifespan function starts the MCP session manager when the server boots so the `/mcp` endpoint is ready for connections.

**The main pipeline execution.** Inside `orchestrator.process_episode()`, each stage runs in sequence. Before each stage, the run log in SQLite is updated with "started." After each stage completes, it is updated with "completed." If a stage raises an exception (other than the research stage, which is caught and swallowed), the run is marked "failed" in SQLite and the exception propagates up to the caller.

**How data moves.** A URL enters the system. The ingest stage produces an audio file on disk and an episode ID as its return value. Everything downstream uses only the episode ID. The transcribe stage loads the audio path from SQLite (which was stored during ingest), calls Deepgram, and writes the transcript to `data/transcripts/<episode_id>.json`. The extract stage reads that file and writes claims to `data/extractions/<episode_id>.json`. The research stage reads the claims file and writes findings to `data/research_items/<episode_id>.json`. The synthesize stage reads all three prior outputs and writes the brief to `data/briefs/<episode_id>.md`. The delivery stage reads the brief, converts it to HTML, pushes it to Reader, and stores the returned URL in SQLite.

**Hand-offs.** The hand-off between every pair of stages is a file on disk keyed by episode ID. No Python object is passed from one stage to the next. This means each stage could in principle be run days apart, or by different processes, and the system would still work correctly.

**Waiting and blocking.** There are two major blocking waits: the Deepgram transcription call (audio upload plus processing time, typically two to five minutes for a long episode) and the Anthropic AI calls for extraction, research, and synthesis (seconds to a minute or more each, depending on model and load). Both are synchronous: the thread sits and waits. If the Anthropic API is rate-limiting, the retry wrapper adds additional wait time automatically.

**Parallel paths.** Nothing runs in parallel in the main pipeline. All stages are sequential and single-threaded. The only exception is the Research_MCP bridge, which uses a thread pool internally to isolate async code from the synchronous pipeline — but the pipeline itself blocks until that work is complete.

**Completion.** When all stages finish, `orchestrator.process_episode()` calls `state.mark_completed()`, which writes the final Reader URL into the episode record and sets its status to "completed." The function returns a summary dictionary. The CLI prints nothing further (the Rich status messages were already printed during execution). The HTTP server discards the return value. The MCP tool returns it to the client.

---

## 7. What the System Remembers

**The SQLite database** (`data/state.db`) is the system's long-term memory. It remembers every episode it has ever processed: the show name, episode title, audio file path, transcript path, brief path, Reader URL, the profile used, the final status, any error message, and when the episode was created and completed. It also remembers the outcome of each stage in a separate log table. This memory is permanent and survives restarts. If the database is lost or corrupted, the system loses its deduplication knowledge — it would reprocess episodes it has already handled — but all the output files (audio, transcripts, briefs) remain on disk and could be re-entered manually.

**Cached files on disk** are a secondary memory. The audio file, the JSON transcript, the extracted claims, and the research results all persist between runs. If you re-run a stage after it has already completed, the stage typically checks for an existing output file and skips re-processing. For transcripts specifically, the cache check is explicit: if `data/transcripts/<episode_id>.json` exists, Deepgram is not called again. This makes it cheap to re-run synthesis or delivery without repeating the expensive steps.

**The `.env` file** holds the system's credentials: the Anthropic API key, the Deepgram API key, the Readwise token, and the optional HTTP server authentication token. These are loaded fresh each time the system starts and are never persisted anywhere by the system itself.

**Nothing is kept in memory between runs.** Each invocation starts cold. There is no in-memory cache, no running daemon that holds state, and no session persistence. The only thing connecting one run to the next is the SQLite database and the files on disk.

---

## 8. What the System Talks To

**Deepgram** is the transcription service. The system sends it the full audio file as a binary upload and receives back a structured JSON transcript with speaker diarization. If Deepgram is unavailable or the API key is missing, the transcription stage fails and the entire pipeline stops.

**Anthropic** is the AI provider for all language model calls. Three model tiers are used: Haiku for speaker name resolution, Sonnet for claim extraction, and Opus for synthesis. All calls go through the central gateway in `core/llm.py`, which retries on rate-limit and server errors. If Anthropic is unavailable for more than five retries, the call fails and the stage errors out.

**Research_MCP** is an external package that the research stage delegates to. It is not developed inside this repository, is not listed in the project's declared dependencies, and was not found installed in the local virtual environment during this review. The research stage will fail if this package is not separately installed. When it fails, the orchestrator catches the failure, warns, and continues without research data.

**Readwise Reader** receives the final brief via their v3 save API. The system sends the HTML content, title, source URL, author, and tags. Reader responds with a URL to the saved document. If Reader is unavailable, the markdown brief remains on disk but is not pushed to the inbox. The system catches this failure and does not abort the run.

**YouTube / Podcast Hosts** are accessed by yt-dlp during the ingest stage. The yt-dlp library handles authentication and protocol negotiation for dozens of platforms. If a URL cannot be downloaded by yt-dlp, the ingest stage falls back to a direct HTTP download. If that also fails, the stage errors out.

**RSS Feeds** are polled directly via HTTP during the `poll` command and the `browse` command. The system reads the feed XML and extracts episode titles, publication dates, and audio URLs.

**The filesystem** is the central hub that connects all stages. Every stage reads from and writes to a local directory tree under `data/`. The system assumes this directory is writable and that enough disk space exists for audio files (which can be several hundred megabytes each).

---

## 9. What Is Currently Built vs. What Is Not Yet Built

**Fully working and complete:**

The entire six-stage pipeline is implemented and appears functionally complete: ingest, transcribe, extract, research (when Research_MCP is installed), synthesize, and deliver. The CLI with all five commands is complete. The FastAPI HTTP server with iOS Shortcut support is complete. The MCP server with the full tool set is complete. The SQLite state management is complete. The retry logic is complete. The three show profiles and their synthesis prompts are complete. The disk-as-bus architecture connecting stages is complete.

**Exists but has a critical undeclared dependency:**

The research stage depends on an external package called `research_mcp` that is not listed in `pyproject.toml` and was not found installed in the local virtual environment. This means `pip install podcast-brief` would produce a system where the research stage silently degrades on every run. The package must be installed separately by someone who knows it is needed. The `agent_playbook.md` mentions Research_MCP by name, which confirms it is an intentional dependency, but its absence from the declared dependencies means it can be silently missing.

**Dead code present in the repository:**

Three files — `research/academic.py`, `research/news.py`, and `research/books.py` — are fully implemented modules from a previous version of the system that queried Semantic Scholar, arXiv, Brave Search, and Google Books directly. They are no longer called from anywhere. They remain on disk but serve no purpose in the current system. `WORKFLOW.md` and the internal code comments explicitly note they are superseded.

**Documentation that misrepresents reality:**

`MCP_PLAN.md` describes the MCP decomposition as "approved plan, not yet implemented" — but the implementation is complete. Every file described in that plan exists in the codebase with matching functionality. The document's status header is stale. Similarly, the README's "Project layout" section describes an old flat `src/` structure that no longer exists; the actual structure uses `core/`, `ingestion/`, `transcription/`, `extraction/`, `research/`, `summarisation/`, `delivery/`, and `interface/` directories.

**Planned but not yet built:**

`V3_PLAN.md` describes a future agentic architecture in which each pipeline stage becomes a multi-step agent with its own triage, scoring, and aggregation logic, and stages communicate through a memory layer rather than raw JSON files on disk. None of this is built. The agent directories, memory layer, and per-agent MCP tools described in the plan do not exist.

**The `trusted_sources.yaml` whitelist** is loaded by `core/config.py` and was used by the now-superseded `research/news.py` crawler. The active Research_MCP path does not consult this file. It remains in the repository but has no effect on the current system.

---

## 10. The Current State of the Project

This project is a well-engineered personal tool that is functionally complete for its primary purpose: turning podcast episodes into research briefs in Readwise Reader. The architecture is clean and coherent. The disk-as-bus pattern is a smart choice for a single-user pipeline — it makes each stage independently restartable, cacheable, and inspectable without any complex messaging infrastructure. The MCP interface is a genuine differentiator: most personal pipelines are CLI-only, but this one is addressable by AI clients, which opens up interactive and automated workflows.

The strongest part of the system is the core pipeline: the stage contracts are well-defined, the retry logic is robust, and the failure behavior is sensible (degrade, don't abort). The synthesis prompts are thoughtfully differentiated by profile — the academic, current events, and hybrid templates each have a distinct structure appropriate to their content type.

The most fragile part is the research stage. The Research_MCP dependency is undeclared, which means the system as shipped will silently skip research on every run until the dependency is manually discovered and installed. Three files of dead code from the previous research approach remain in the `research/` directory, which makes that directory misleading — two of the four files do nothing. Anyone picking up this codebase would reasonably read `academic.py`, `news.py`, and `books.py` and believe the system uses them.

The documentation situation is mixed. `WORKFLOW.md` is accurate and useful. `MCP_PLAN.md` is stale (the plan is done). The `README` project layout section is stale (it describes the old structure). `V3_PLAN.md` is clearly marked as a future plan and is honestly speculative.

For someone picking this up for the first time: install the package, set up the `.env` file with API credentials for Anthropic, Deepgram, and Readwise, and then separately locate and install the Research_MCP package if you want the research stage to work. Run `podcast-brief check` to verify your credentials before your first run. The three dead crawler files in `research/` can be ignored or deleted without any effect on the system. The `V3_PLAN.md` describes where the project wants to go next but nothing there is started.
