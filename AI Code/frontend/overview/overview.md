# AI OS — Codebase Overview

**Last updated:** 2026-05-31

---

## 1. What This Project Is

This repository is not a single application. It is a personal AI toolbox — a collection of roughly ten independent projects, each built by one developer (Aryaman) to solve a specific slice of everyday life using AI. Think of it as a workbench with many specialized tools hanging on it: a calendar assistant, a spending tracker, an academic research tool, a podcast summarizer, a study-card system, a Chrome extension for critical reading, and a few more. They share a theme (AI-assisted personal productivity on macOS) but largely run independently and talk to different AI providers.

---

## 2. The Big Picture — How It All Fits Together

Picture a desktop workspace with seven distinct assistants, each a separate room:

**The Planner** is the most central room. It is a chat interface that lets you talk to your Apple Calendar and Apple Reminders in plain English. You tell it "block two hours for writing on Thursday afternoon" and it checks your calendar, proposes the event, and only touches your calendar after you approve. It knows what you did yesterday because it saves every conversation to markdown files in your Obsidian vault, and loads the highlights at the start of each new session. The Planner is also aware of your spending, because the UPI Agent (described below) feeds it transaction data it can answer questions about.

**The UPI Agent** is the financial room. It reads your iPhone's SMS messages (which flow to your Mac via iMessage), extracts UPI payment notifications automatically, and builds a local spending ledger. It categorizes every transaction — first by learning your past patterns, then by matching merchant names, then by looking at what was in your calendar around the time of the payment (so a payment while a gym session was on your calendar is probably tagged "Health"). You can review and correct categories through a small web dashboard, and those corrections teach the system. Once a week it writes a narrative summary of your spending in plain English.

**The Research MCP** is the library. It is a research assistant that any AI agent can call via a standard protocol (MCP stands for "model context protocol," a way for AI tools to talk to each other). You give it a topic, and it fans out across academic paper databases, preprint servers, Wikipedia, the open web, and Google Books simultaneously, deduplicates what it finds, scores each source for credibility, and writes a cited essay. It can also take a paragraph of claims and decide, source-by-source, which ones need correction and which are probably fine.

**The Podcast Brief** is the reading room. Point it at a podcast episode URL, and it downloads the audio, transcribes it word-for-word, extracts the factual claims made by the speakers, looks up supporting academic papers and news articles for each claim, and then synthesizes everything into a rich reading brief that gets pushed to your Readwise Reader account. If you prefer, it can also just give you the raw transcript.

**The Study System** is the classroom. It is built for CFA Level 1 exam preparation. It reads your Obsidian notes, uses an AI to extract structured concepts and factual statements from each file, generates flashcards and multiple-choice quiz questions, and then runs timed review sessions in the terminal where it tracks how well you remember each card using a scheduling algorithm that adapts to your forgetting curve.

**Sharpen** is the browser companion. It is a Chrome extension that lives in the side panel of your browser. On any webpage you are reading, you can ask it to generate steelmanned counterarguments to the page's claims, identify loaded language and rhetorical framing, summarize the page in thirty seconds, or enter a live debate with an AI that argues the opposite of whatever position you stake out. Everything happens through the OpenAI API.

**The Optimizer** is a prompt and plan editing assistant. It takes a raw AI prompt or a technical plan, breaks it into named sections, and lets you chat with an AI about any individual section — rewriting it, asking why it was written that way, or getting the AI to flag contradictions between sections. It works through a backend API (currently `app_1.py`) that is fully implemented on the server side, though the web interface to drive it still needs to be built.

Beyond these seven main rooms, there are also smaller utilities: a one-off script that migrates Notion pages into your Obsidian vault, an experimental agent that drives a drawing application by generating mouse clicks, and a scaffolded Next.js frontend for the Optimizer that currently shows only a test button.

---

## 3. Every Component — What It Does and Why It Exists

### Planner and Reminders (Core)

The Planner is a chat assistant that understands scheduling. Its heart is a FastAPI web server (`app.py` at the project root) that serves a single-page HTML frontend. Every message you type is sent to this server, which builds the full conversation history and passes it to the OpenAI GPT-4o model. The model can call tools — check the calendar, check your reminders, create an event, create a reminder, move an event, delete an event, or query your UPI spending — and the server decides whether to execute those tools immediately or pause and show you a confirmation card.

The critical design choice is the distinction between read tools and write tools. Read tools (checking the calendar, fetching reminders, looking up spending data) execute automatically without interrupting you. Write tools (creating, moving, or deleting anything) always pause and ask for your approval before touching your calendar. This is enforced in the agent loop in `planner.py`, which iterates the model call in a cycle: get a response, execute any reads, and either loop with the results if only reads were requested, or stop and surface the write proposals to you.

When you approve a batch of writes, the server executes them one by one and maintains a rollback stack — so if the third item in a batch fails, it reverses the first two rather than leaving things half-done. It also maintains a sync-state file that links related reminders to their parent events, so that when you move an event, it queues up matching reminder reschedules automatically.

The memory system (`memory.py`) saves each conversation to a dated markdown file in your Obsidian vault. When a new session starts, it loads the "carry-forward notes" from the past seven days — bullet points the model distills from each session about unresolved commitments, preferences, and follow-ups. The most recent full conversation is also included if there is room within an 8,000-character budget. A sanitization pass strips lines that look like prompt-injection attempts before any memory content is loaded into the system prompt.

The daily scan (`scan.py`) is triggered by a button in the interface. It reads your full calendar and reminders, does objective pre-analysis in Python (finding overdue todos, conflicts, overloaded days), and passes this structured report to the agent loop, which generates a morning briefing and queues any proposed reschedules through the same confirmation flow.

The calendar and reminders are controlled through AppleScript — small programs written in Apple's own scripting language that talk directly to Calendar.app and Reminders.app. These are executed via a macOS system mechanism that does not create child processes the unsafe way, which matters because a known bug in Python on macOS causes crashes if you fork a process after certain AI libraries have loaded.

### UPI Agent (Core)

The UPI Agent is a local payment tracker with no external network calls beyond an optional AI-written summary. It reads your iPhone's SMS messages from a file that macOS maintains at a fixed path when iMessage is configured to relay messages from your phone. It opens this file in read-only mode to be safe, pulls messages that arrived since the last time it ran, and processes each one.

The parser extracts payment details — amount, direction (sent or received), the counterparty's payment address, bank name, and reference number — using regular expressions tuned for the SMS formats used by Indian banks. Messages that are OTPs, promotional texts, or balance alerts are discarded.

For each genuine payment, the agent queries your Apple Calendar to find any events that were happening in the thirty minutes before or after the payment. These events are stored alongside the transaction, giving context ("you paid for something while a Gym session was in your calendar") that helps with categorization later.

Categorization is handled by a four-way ensemble. The history classifier looks up past decisions for the same payment address or merchant-name fragments. The merchant classifier matches the counterparty name against a hand-curated list of patterns. The calendar classifier checks whether the surrounding events match any keyword groups. The heuristic classifier applies weak tiebreakers based on amount and time of day (a small payment in the morning is probably food; a large round number in the first five days of the month might be rent). Each classifier produces weighted votes, and the system assigns a category if the winning vote clears a confidence threshold. User corrections through the dashboard feed back into the history rules, so the system learns from disagreements.

The dashboard (`dashboard.py`) is a small FastAPI web server that lets you browse your transaction feed, triage uncategorized payments, review spending goals, and export data. It is designed to be mounted inside the main Planner server as a sub-application at the `/upi` path — but only if the right package structure is in place (more on this in section 9).

A separate tax layer handles importing bank statements from SBI in their exported spreadsheet format, which is technically an Excel file but actually tab-delimited text inside a renamed container. The parser handles this quirk.

A launchd configuration file is provided to schedule a weekly narrative summary on Sunday evenings using the macOS task scheduler.

### Research MCP (Core)

The Research MCP is a backend research service that any AI tool can call via the MCP protocol — the same protocol Claude Code uses to call tools. It exposes nine tools: two high-level ones (research a topic, verify claims in a brief) and seven lower-level ones that let you query individual sources directly (Semantic Scholar, arXiv, Wikipedia, Brave Search, Google Books).

When you ask it to research a topic, the engine first runs a "triage" step that assesses the nature of the question — is it a factual claim, a topic for exploration, something that can be verified quickly, or something that needs deep investigation? This uses Claude to reason about the question and decides how much effort to spend.

For a deep run, the engine expands the topic into several related search queries, fires them all against all configured sources simultaneously, merges the results to remove duplicates (using fingerprints computed from each source's URL and title), stores new sources in a SQLite database with a unique identifier per source, asks Claude to annotate each one for relevance and credibility, and then synthesizes everything into a cited essay using a structured prompt. After synthesis, a citation gate verifies that every source tag in the essay actually corresponds to a real source in the results — preventing the AI from hallucinating citations.

Every AI call is metered through a `MeteredClient` wrapper that records token counts, cost in USD, and timestamps both to a SQLite database and to a daily append-only audit log file. This lets you see exactly what research ran and what it cost.

Credibility is controlled by a trusted-sources configuration file. When the `trusted_sources_only` flag is set, the Brave Search client filters web results to a whitelist of domains. arXiv, Semantic Scholar, and Wikipedia are always unrestricted.

### Podcast Brief (Core)

The Podcast Brief pipeline processes a podcast URL end to end. The ingestion step downloads the audio file using `yt-dlp`, a universal video/audio downloader. The transcription step sends the audio to Deepgram's Nova-3 model, which returns a timestamped, speaker-attributed transcript. The extraction step sends the transcript to Claude Sonnet, which identifies factual claims and categorizes them by type. The research step routes those claims to academic databases, news search, or books depending on the "profile" configured for the show (academic, current events, or a hybrid of both). The synthesis step sends everything — the transcript, the claims, and the research findings — to Claude to write a reading brief in markdown. The delivery step converts the markdown to HTML and pushes it to your Readwise Reader account via their API.

Every episode is tracked in a local SQLite database, so re-running the pipeline on an already-processed episode is a no-op. Each stage is logged, and failures at any stage mark the episode as errored in the database.

Show configurations live in a YAML file, letting you pre-define which profile to use, how many speakers a show typically has, and other per-show defaults. A polling component can monitor an RSS feed and trigger the pipeline automatically when new episodes appear.

### KG and Study System (Core)

The study system is a CFA Level 1 exam preparation tool built around an Obsidian vault. When you run the ingest command, it scans your vault, computes a hash of each file's content, and identifies which files are new or changed since the last run. For each changed file, it calls Anthropic Claude to extract structured knowledge: a list of concepts, relationships between concepts (called triplets, as in "subject — relation — object"), and atomic facts. This extraction happens once per file and is cached in a SQLite database, so you do not pay the AI cost again unless the file changes.

For each extracted concept, it generates flashcards using OpenAI GPT-4o-mini and optionally generates multiple-choice quiz questions. A quality pass samples twenty percent of the cards and checks whether they are grounded in the source text (rather than hallucinated) and whether they meet a rubric for quality.

During review sessions, the system pulls cards that are due based on the FSRS-4.5 scheduling algorithm — a modern spaced repetition algorithm that adapts the interval between reviews based on how well you rated each card (Again, Hard, Good, or Easy). The algorithm tracks stability (how robust the memory is) and difficulty (how hard the card is for you personally) and computes when you should next see each card to review it just before you would forget it.

The knowledge graph component extracts the triplet relationships and lets you review them manually, approving or rejecting each proposed edge. A graph library (NetworkX) maintains the approved edges in memory and runs cycle detection to prevent circular prerequisite chains.

A vector store using ChromaDB stores embeddings of concepts and atomic facts for similarity search — though this component is marked as incomplete: the retrieval function always returns an empty list in the current code.

### Sharpen Chrome Extension (Core)

Sharpen is a Chrome extension that opens in a side panel when you click its toolbar button. It has four modes, selectable via tabs.

The Counterarguments mode reads the current page's text (up to 6,000 characters), sends it to OpenAI, and returns a structured breakdown: the main claims of the article, steelmanned counterarguments for each claim rated by strength, the article's weakest points, and important context the article omits.

The Bias mode analyzes the same text for rhetorical structure rather than factual claims: framing choices, loaded language with exact phrases quoted, what the article emphasizes versus ignores, implicit assumptions it makes, and persuasion techniques it uses. It explicitly discourages the model from labeling anything as "false" — the goal is pattern recognition, not fact-checking.

The Debate mode extracts the central debatable topic from the page, takes your stated position as input, and argues the direct opposite of your position through a live chat. The AI is instructed to never capitulate just because you push back and to press on weak points in your arguments. The debate is maintained in memory across the session and can be saved as a markdown file.

The TL;DR mode streams a structured summary with a bottom line, a two-to-three sentence overview, key points, and a note on who would benefit most from reading the full article. Summaries can also be saved as markdown files to a folder you choose.

All four modes call OpenAI's API directly from the browser extension, with the API key hardcoded in the side panel script.

### app_1.py — The Unified Server (Core)

`app_1.py` is a significantly expanded version of `app.py` that includes the full backend for the Prompt and Plan Optimizer. While `app.py` handles only the Planner and its UPI integration, `app_1.py` adds a complete set of optimizer endpoints. It accepts a raw prompt or technical plan, uses Claude to split it into labeled sections, and then allows per-section chat iteration. Each iteration can rewrite the section, explain the existing content, ask a clarifying question, or suggest a project-context update. After any section edit, it runs a conflict detector that checks whether the new content contradicts, duplicates, or orphans anything in the other sections. It maintains a version history with the ability to snapshot and revert. All optimizer state is held in memory only — there is no database persistence for optimizer documents.

### Supporting components

The Painting Shapes agent is a fully self-contained experiment in AI-driven desktop control. It runs a Google Gemini model as an agent that drives a drawing application (LibreOffice Draw, Keynote, or Paintbrush) by calling an MCP server with tools like "open drawing app," "set canvas corners," "draw circle," "draw square," and "add text." The MCP server tracks the canvas geometry in memory and converts the AI's logical instructions into actual mouse clicks and keyboard events on screen via the macOS accessibility layer. It works end-to-end and is a clean demonstration of the MCP tool-calling pattern applied to desktop automation.

The prompt-plan-optimizer Next.js project is a separate frontend for the Optimizer that was started but not completed. Its library files define the data types, Claude API wrapper, diff utilities, versioning logic, and storage layer needed by a full UI — but the actual page currently shows only a single "Test backend" button to verify the API connection. The backend logic has since been migrated into `app_1.py`, making this Next.js project largely superseded as a standalone frontend.

The Notion to Obsidian script is a single Python file that walks a Notion workspace starting from a hardcoded root page and exports every page and its children as markdown files into a folder in your Obsidian vault. It handles headings, paragraphs, and nested child pages. Both the Notion API key and the destination path are hardcoded in the file.

The Persistent Memory Chats Storage folder is not a codebase — it is a collection of past chat session markdown files and agent memory notes, including notes used by AI agents (like this overview agent) to remember things across sessions.

The top-level static folder contains a single HTML file that appears to be an older version of the Planner's interface.

---

## 4. How a Typical Interaction Works

The most common interaction is using the Planner to schedule something.

You open a browser to `http://127.0.0.1:8000`, which the Planner server is already running at. The page loads a chat window. Before you type anything, the server has already silently fetched today's calendar events and loaded carry-forward notes from your recent conversation history. These are embedded in every system prompt, giving the AI immediate awareness of what is happening in your day and what you discussed recently.

You type something like "I need to prep for my product review on Friday afternoon. Can you set up a two-hour prep block Thursday morning?" The message is sent to the server, which appends it to the conversation history and calls GPT-4o with that history plus the system prompt.

The model decides it should check the calendar before proposing a specific time. It calls the `check_calendar` tool, which the server executes immediately by running an AppleScript that queries Calendar.app. The results — every event in the next seven days — come back as JSON and are fed back into the conversation. The model now sees that Thursday at 10am is free and Saturday has the product review. It formulates a proposal: create a two-hour event called "Product Review Prep" on Thursday at 10am.

Because this is a write operation, the agent loop pauses. The server returns the proposed action to the frontend as a confirmation card below the chat window. You read "Create event: Product Review Prep on 2026-06-04 at 10:00" and click Confirm.

The server executes the AppleScript to create the event in Calendar.app, stores a rollback entry in case something later fails, and then re-enters the agent loop so the model can compose a confirmation message. The response appears in the chat: "Done! Created Product Review Prep on Thursday at 10:00am — two hours before your usual lunch window." The session is saved to your Obsidian vault when you close the browser or click "New session."

---

## 5. How the System Makes Decisions

The central decision in the Planner is whether a tool call should be executed automatically or shown to you for approval. The decision is made by checking whether the tool name is in the "read tools" set or the "write tools" set. This is a hard-coded classification in `planner.py` — there is no inference or ambiguity. Read tools always run silently. Write tools always pause. The model never has the ability to bypass this gate.

A second decision is whether to loop again after a set of read tool calls or to stop and respond. The agent loop stops as soon as the model produces a text response (rather than more tool calls), or when it hits the maximum number of loop iterations. On hitting the maximum, it injects a system message telling the model to summarize only what was confirmed by tool results actually received — preventing it from describing actions as if they happened when they didn't.

In the Research MCP, the key decision is what level of effort to apply to each item. The triage step asks Claude to assess each claim on two dimensions: is it likely correct, incorrect, or genuinely a topic for exploration? And how much work would it take to verify? If the model's confidence in its "light effort" judgment is below seventy percent, the system automatically escalates to "deep" effort. Claims assessed as clearly fine are silently passed without any research at all.

In the UPI Agent's categorization, the decision is whether the winning vote total from the ensemble of classifiers clears a confidence threshold defined in the configuration file. If no category clears the threshold, the transaction remains uncategorized for you to label manually through the dashboard. User labels are the highest-priority signal and are never overwritten by automated classification once set.

In the Study System, the decision of when to next review a card is made by the FSRS algorithm after each rating. The algorithm computes a new "stability" value based on how you rated the card and the current stability, and schedules the next review at the point where there is roughly a ninety percent chance you would still remember it.

---

## 6. How the Code Actually Flows — The Execution Journey

**Planner entry point.** The server starts by running `app.py` (or `app_1.py` for the optimizer-enabled version) with uvicorn, a Python web server. During startup, it tries to import the UPI brain layer — if that import fails (which it always does, as explained in section 9), it logs a warning and continues without it. It then loads the memory context from your Obsidian vault and restores any pending-action state that survived a crash or restart from a small JSON file on disk.

Every incoming chat message arrives as an HTTP POST. The server appends the message to the session's message list, reads today's calendar events via AppleScript, and builds the full OpenAI-format message list by prepending system messages containing the current date, your calendar, and your memory context. It calls the agent loop in a thread (to keep the server responsive while the slow AI call happens).

Inside the agent loop, each iteration: calls GPT-4o with the full message history and tool schema, reads the response, checks whether it is a final text reply or a request to call tools, partitions tool calls into reads and writes, runs reads in parallel threads, appends all read results to the message history, and either loops again or pauses for confirmation. The loop runs a maximum of eight times before forcing a text response.

When the user confirms a write action, the server executes each tool call in sequence, building and potentially executing a rollback stack if any item fails. It then re-enters the agent loop with the tool results appended, so the model can produce a follow-up confirmation message.

**Research MCP entry point.** The server starts by initializing the SQLite database and then begins listening on standard input/output for MCP protocol messages. An MCP client (such as Claude Code) sends a tool call, the server routes it to the engine, the engine runs the research pipeline asynchronously, and the result is returned over the same connection.

**Podcast Brief entry point.** The CLI calls `run_pipeline` directly. The pipeline runs stage by stage in sequence, updating a SQLite state record after each stage. If a stage fails, the episode is marked as errored and the exception propagates. All external calls (Deepgram, Claude, research APIs, Readwise) are synchronous and blocking in sequence.

**UPI Agent entry point.** The agent is run from the command line. It reads the state file to find the last-processed SMS row ID, opens the iMessage database in read-only mode, fetches new messages, and processes them one by one. For each UPI message, it runs the parser, calls AppleScript for calendar context, and upserts the result into the local SQLite database. After the main loop, it calls the reactor, which runs the classifier and anomaly detectors on the newly inserted payment IDs. The state file is updated with the new high-water mark.

---

## 7. What the System Remembers

The Planner keeps two kinds of memory. In-session memory is the live list of messages held in a Python dictionary in the server process — it disappears if the server restarts (though pending actions are written to a JSON file on disk to survive crashes). Across-session memory is the collection of markdown files in your Obsidian vault, from which carry-forward notes and the most recent full conversation are loaded at startup.

The UPI Agent's memory is a SQLite database at `~/.upi-agent/data.db`. This is the permanent ledger of every transaction ever imported. It also maintains a `state.json` file at the same path recording the highest SMS row ID processed, so re-runs always start from where the last run left off without re-importing old messages.

The Research MCP remembers all sources and runs in a SQLite database under the project's `data/` folder. Every source that has ever been fetched is stored with its fingerprint, so future research runs can retrieve cached annotations rather than re-annotating the same paper. Run records are also stored, including costs and status.

The Podcast Brief tracks each episode by ID in a local SQLite database, preventing double-processing.

The Study System stores the vault manifest, all extractions, concepts, cards, review history, quiz history, spending on AI calls, and quality-check results in a single SQLite database. The FSRS state for each card (stability, difficulty, due date) is stored as columns on the card row and updated after every review.

The Sharpen Chrome extension stores only one thing across sessions: the handle to a folder you choose for saving markdown files (stored in the browser's IndexedDB). Everything else is session-only — closing the side panel clears the debate, the analysis results, and any conversation history. Debate transcripts are exported to a file before the panel closes.

The Optimizer (in `app_1.py`) keeps all document state in a Python dictionary in memory only. Closing or restarting the server wipes all documents and chat histories. Snapshots can be created for in-session version history but are not persisted anywhere.

---

## 8. What the System Talks To

**Apple Calendar and Apple Reminders** — talked to via AppleScript scripts executed as system subprocesses. The Planner reads and writes events and reminders; the UPI Agent reads calendar events for transaction enrichment. Unavailable if the user has not granted Automation permissions in System Settings.

**OpenAI API** — called by the Planner (for chat and memory generation), the Sharpen Chrome extension (for all four analysis modes), and the Study System (for card generation, quality checks, and embeddings). If unavailable, the Planner fails to respond to messages, Sharpen shows an error, and the Study System cannot generate new cards.

**Anthropic API** — called by the Research MCP (for all AI reasoning steps), the Study System (for knowledge extraction from vault files), and the Optimizer in `app_1.py` (for section splitting, iteration, conflict detection, and context extraction). The Research MCP also accepts Anthropic as a dependency for synthesis in the Podcast Brief pipeline.

**Google Gemini API** — called exclusively by the Painting Shapes agent runner. Not used by any other component.

**Deepgram** — called by the Podcast Brief for audio transcription. If unavailable, the pipeline fails at the transcription stage.

**Semantic Scholar and arXiv** — called by both the Research MCP and the Podcast Brief's research stage. These are public APIs that do not require keys for basic use. If unavailable, the research stage skips those sources without failing.

**Wikipedia** — called for lookup by both the Research MCP and Podcast Brief. Public, no key required.

**Brave Search** — called by both the Research MCP and Podcast Brief for web search. Requires an API key. If the key is missing, the source is silently omitted.

**Google Books** — called by the Research MCP and Podcast Brief for book lookup. Requires an API key. If the key is missing, the source is silently omitted.

**Readwise Reader** — called by the Podcast Brief to push finished briefs and transcripts. Requires an API key. If unavailable, the final delivery stage fails even though the transcript and brief have already been written to disk locally.

**Notion API** — called by the Notion to Obsidian migration script. The key is hardcoded in the script file.

**iMessage chat.db** — read in read-only mode by the UPI Agent. This file lives at a fixed path in the user's home directory and is populated automatically by macOS when iMessage SMS forwarding is configured. If the file does not exist or Full Disk Access permission is not granted, ingestion fails.

**ChromaDB** — used by the Study System for vector embeddings. ChromaDB stores data locally on disk. If the Python package is not installed, the vector store degrades gracefully and the rest of the system continues without embeddings.

**The local filesystem (Obsidian vault)** — the Planner writes memory files to a hardcoded path inside the Obsidian vault. The Study System reads from a vault path configured in an environment variable. The Podcast Brief writes briefs and transcripts to a local directory.

---

## 9. What Is Currently Built vs. What Is Not Yet Built

**Fully working and complete:**

- The Planner chat interface, agent loop, confirmation flow, rollback logic, sync state, memory system, and daily scan
- The UPI Agent ingestion pipeline, categorization ensemble, learning loop, anomaly detection, goal tracking, spending narrative, and SBI statement import
- The UPI dashboard with transaction feed, triage, and tax views
- The Research MCP with all nine tools, full deep and light pipelines, deduplication, annotation, synthesis, and citation verification
- The Podcast Brief pipeline end-to-end (ingest, transcribe, extract, research, synthesize, deliver)
- The Sharpen Chrome extension with all four modes (counterarguments, bias, debate, TL;DR)
- The Study System ingest pipeline, flashcard generation, review session (FSRS scheduling), MCQ quiz, knowledge graph edge review
- The Optimizer backend in `app_1.py` (section splitting, iteration, conflict detection, context extraction, version history)
- The Painting Shapes drawing agent

**Exists but incomplete or has notable gaps:**

- The `prompt-plan-optimizer` Next.js frontend: the library scaffolding exists (types, API wrapper, diff, versioning, storage) but the UI is one test button. The optimizer backend has since been built into `app_1.py`, making this project partially superseded.
- The Study System's vector store: ChromaDB is integrated for storing embeddings, but the function that retrieves atomic facts by similarity always returns an empty list — so vector search is write-only and cannot be used for retrieval yet.
- The Study System's FSRS retraining: `maybe_retrain()` is a stub that never runs, so the scheduling algorithm uses the same fixed default weights forever rather than adapting to the user's personal forgetting patterns.
- The Study System has a cost ceiling configuration setting that is never enforced — a runaway ingest will not stop at the spending limit.
- The Study System Phases 3 through 5 (director session planning, Feynman evaluation mode, briefing mode, planner integration) are not started.

**Planned or referenced but does not yet exist:**

- A `brain/` package at the project root that `app.py` and `app_1.py` both try to import for UPI integration. No such directory exists. Both files handle this with a `try/except` that silently disables UPI features, logging a warning. As a result, the `/upi` dashboard is never mounted and UPI data is never ingested through the Planner's daily scan — the UPI Agent must be run separately. This is a broken integration, not a working feature.
- A WhatsApp interface for the Planner (described in planning documents as a future replacement for the browser frontend).
- A proper web frontend for the Optimizer (the `static/index.html` at the project root serves the Planner interface, not the Optimizer).

**Security issues worth noting:**

- The Sharpen Chrome extension has an OpenAI API key hardcoded directly in its source code. Anyone who installs this extension or reads the source file has that key.
- The Notion to Obsidian script has a Notion API key and a personal page ID hardcoded in plain text.

---

## 10. The Current State of the Project

This is an active personal-use toolkit at the transition point between "experiments that work" and "reliable daily tools." The Planner is the most polished and architecturally thoughtful component — the agent loop design, confirmation flow, rollback logic, and memory system are production-quality thinking applied to personal tooling. The UPI Agent is also mature, with a real test suite of 74 tests, a learning loop, anomaly detection, and a tax layer that handles real-world messiness like banks producing fake Excel files.

The Research MCP and Podcast Brief are functional and well-structured pipelines, each with clear stage boundaries and good error handling. The Study System has a solid foundation for the CFA prep use case (phases 1 and 2) but has multiple known architectural issues documented honestly in its own overview file — cost ceiling not enforced, FSRS not adapting, vector retrieval not working.

The most fragile part of the project is the integration between components. The UPI Agent is meant to be embedded into the Planner server through a `brain/` package import that references a non-existent directory, meaning the integration simply never works. The Optimizer backend exists in `app_1.py` but has no production frontend. These are integration seams that were designed but not yet wired.

Someone picking this up for the first time should know: each project is almost entirely self-contained and can be understood and run independently. The Planner needs `Planner and Reminders/Calendar and Reminders/` on the Python path and an OpenAI API key in `.env`. The UPI Agent needs only its own directory and the iMessage database to exist. The Research MCP needs an Anthropic key and optionally Brave/Google Books keys. None of these depend on each other at runtime — the intended integrations are aspirational rather than functional.
