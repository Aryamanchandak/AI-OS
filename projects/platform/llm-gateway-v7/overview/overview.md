# LLM Gateway V7 — Current Codebase Overview

Last updated: 2026-08-02 00:00 IST

## 1. What This Project Is

LLM Gateway V7 is a small personal service that gives other programs one consistent way to ask several different language-model providers for chat responses or vector embeddings. It hides the providers' incompatible request and response formats, chooses an eligible provider, records what happened, and returns one common response shape. Its current direction is explicitly narrower than its older versions: it is infrastructure for calling models, not an agent, a tool runner, a web dashboard, or an AI model that decides which other AI model should work.

## 2. The Big Picture — How It All Fits Together

The easiest way to picture the gateway is as a reception desk shared by several specialist offices. A caller hands the receptionist either a chat request or a request to turn text into a numerical search representation. The receptionist checks what kind of work was requested, consults a list of offices that are open and suitable, sends the work to one office, translates the answer into the house format, and writes an entry in a ledger.

For chat, the available offices are provider adapters for Gemini, OpenAI, Anthropic, and optional local Ollama models. Each cloud vendor can be switched on or off independently and is only present when its access key is configured. Local Gemma chat is now off by default because loading it is expensive on a laptop. A separate local Phi-4 model can be enabled specifically for document segmentation. The normal provider order begins with the three Gemini tiers, continues through three OpenAI tiers, and ends with three Anthropic tiers. An environment setting can replace that order.

The file still called `router.py` is not the old AI classifier. It is now closer to the receptionist's availability board. It walks the configured provider order and skips providers that lack a requested capability, cannot fit the estimated request, have exhausted a configured rate allowance, or are temporarily backed off after an error. Once it selects a provider, the gateway makes one real provider call. If that call itself fails, chat returns the failure; it does not try a second provider. This distinction matters: selection can skip a provider before a call, but there is no runtime chat failover after a chosen provider errors.

Callers can bypass the normal order by naming a provider or a shortcut. They can also use a chat profile. A profile is a named route for a specific use. `knowledge-extraction-v1` normally selects Anthropic Sonnet, although its provider may be changed by configuration. `document-segmentation-v1` is stricter: it selects only the optional local Phi-4 provider, whose exact model is fixed in the registry. If Phi-4 is disabled, the profile fails rather than quietly using a cloud model.

Every chat adapter performs two translations. On the way out, it converts the gateway's common messages, system instructions, tools, structured-output request, and reasoning preference into the provider's native protocol. On the way back, it converts text, token usage, stop reasons, and model-generated tool calls into a common response. The gateway never runs those tools. A surrounding harness or MCP server owns tool registration and execution. The gateway's role is only protocol translation and normalization.

Structured output is another cross-provider layer. A caller supplies a description of the required JSON shape. The adapter asks the provider for constrained JSON where the provider supports it, and the gateway independently validates the returned text against the caller's original description. If validation fails, it makes one repair request to the same provider. This happens for both the ordinary and nominally streaming paths, although the repair logic is duplicated and the provider adapters currently simulate streaming by waiting for a complete response before yielding it.

Embeddings travel through a separate pipeline. The default order is local Ollama using `nomic-embed-text`, then Gemini using `gemini-embedding-001` when a key exists. Both are configured to return 768 numbers, and the gateway rejects inputs over 8,000 characters rather than truncating them. Embedding calls do have runtime failover when no provider is pinned. They also have their own cooldown and escalating short backoff state, separate from chat.

The embedding profile `chunker-v1` pins calls to the local Ollama model at 768 dimensions. The server verifies both the returned model name and width and fails loudly if either differs. This is safer than relying on a provider name because changing an embedding model can corrupt a vector index even when the numerical width stays the same. The README's claim that same-width Ollama and Gemini vectors are automatically interchangeable should not be treated as a mathematical guarantee; matching dimensions alone does not establish that two different models share one vector space.

The service keeps two kinds of memory. Short-lived in-memory state tracks recent calls, cooldowns, backoff windows, and Gemini cache references; all of that disappears on restart. A SQLite database is the durable ledger. It stores provider, model, success or error, latency, token and character counts, tool-call information, selected overrides, skipped candidates, call role, embedding width, and profile. Status and history endpoints expose this operational picture without a web interface.

The included Python client is a thin convenience wrapper around the HTTP API. In addition to chat, streaming, embeddings, status, and capability queries, it can resolve a chat profile and perform a real preflight check. Preflight deliberately makes one small structured chat call and one embedding-profile call, so it tests actual reachability rather than merely asking whether configuration appears healthy.

## 3. Every Component — What It Does and Why It Exists

### The service and request pipeline

`main.py` is the center of the system. At startup it creates or upgrades the call-log database, initializes the short-lived Gemini cache, builds the enabled chat providers, constructs the provider-selection board, and builds the embedding providers. It exposes the HTTP endpoints and owns the end-to-end chat and embedding journeys. It normalizes incoming messages and system instructions, estimates request size, determines required capabilities, resolves profiles, invokes providers, validates structured results, applies backoff after failures, records calls, and shapes responses. Without it, the other modules are useful parts with no running service around them.

The chat handler has begun to acquire small helpers for message normalization, system preparation, token estimation, capability requirements, structured validation, backoff selection, and profile resolution. The central handler is still large, however, and contains separate streaming and non-streaming validation-and-repair paths. That is why the cleanup notes still call for a deeper split rather than a rewrite.

### Provider adapters

`providers.py` is the largest and most protocol-sensitive component. It contains adapters for OpenAI, Anthropic, Gemini, and Ollama, plus the registry builder that creates named cheap, middle, and high-end cloud tiers. The adapters translate the common request into each vendor's message, tool, reasoning, cache, and structured-output conventions, then normalize the answer back into one contract.

OpenAI uses native function calls and native JSON response formats. Anthropic converts assistant and tool turns into content blocks, uses native tool calls, and now uses Anthropic's direct structured-output format. Because Anthropic accepts only part of the full JSON Schema language, the adapter makes a provider-safe copy: unsupported bounds become descriptive guidance and object shapes are closed, while the untouched caller schema remains the final validator. Gemini translates tool calls and tool results, preserves its special thought signature for later turns, supports provider-side JSON shaping, and can use explicit cached system content. Ollama uses native tool calling for known capable model families and a prompted JSON fallback for other models.

The module exists because sending one vendor's format to another would fail or, worse, silently change meaning. It is currently one 1,086-line file, so the cleanup direction suggests splitting it by backend if it grows further.

### Provider selection and rate state

`router.py` contains provider names, aliases, configured limits, volatile usage state, and the selection walk. It prevents calls from being sent to a provider that is known to be unsuitable or temporarily unavailable. Its name is historical: no language model classifies requests here anymore. The module also contains an asynchronous lock that is not currently used, and its counters exist only in one running process, so multiple gateway processes would not share a single quota view.

### Embeddings

`embedders.py` owns the embedding-specific providers, the fixed 768-number output policy, the `chunker-v1` profile, the 8,000-character ceiling, and embedding-only rate and backoff state. It adds the task prefix expected by the local model, uses Gemini's native retrieval task settings, and implements sequential failover when the caller has not pinned a provider or profile. This is deliberately separate from chat because its models, quotas, failure policy, and compatibility risks are different.

### Public data shapes and client

`schemas.py` defines the common envelopes accepted and returned by the server. It includes chat and embedding profiles, model-generated tool definitions and calls, cache-marked system blocks, structured-output descriptions, normalized stop reasons, token counts, and parsed JSON. The old `auto_route` and router-decision shapes are absent.

`client.py` is the small synchronous Python client intended for reuse by other projects. It calls the server rather than reproducing provider logic. Its notable additions are embedding-profile support, status and embedder discovery, chat-profile resolution, and preflight. It does not yet contain the planned generic helper that accepts an arbitrary caller-supplied Pydantic class and directly returns a validated instance.

### Durable logs and short-lived cache

`db.py` creates and writes the local `gateway_v7.db` SQLite ledger and performs limited in-place upgrades for the embedding-width and profile columns. It supplies recent-call and daily aggregate views used by the HTTP status endpoints. If this database is lost, the gateway can still make calls, but its audit and performance history disappears.

`cache.py` keeps a five-minute in-memory map of long Gemini system instructions to upstream cache resources. It quietly falls back to sending normal system text when cache creation fails. Restarting the gateway forgets the local references; provider-side resources expire independently.

The tests are supporting evidence rather than runtime components. The most important groups verify registry switches and the one-attempt chat rule, exact chat profiles, embedding behavior and profiles, preflight aggregation, and provider-specific tool and structured-output translation. Packaging and dependency files are peripheral; they currently advertise version 0.2.1, although their summary still describes the project as "V3 plus an embed endpoint," which no longer captures the cleanup.

## 4. How a Typical Interaction Works

For a normal chat call, another program sends a prompt or a list of messages. The gateway turns a lone prompt into a user message, prepares any system instructions, and estimates how much context the request plus requested answer may consume. If the caller named a chat profile, the gateway resolves it and refuses conflicting provider or model overrides. It determines whether the request requires tools, reasoning, or structured output, then walks the explicit provider or configured provider order.

Candidates may be skipped before any network call because they lack a required feature, cannot fit the estimated context, are in cooldown or backoff, or have crossed a configured rate allowance. The first eligible provider is selected and marked as used. The matching adapter translates the conversation and makes the network or local Ollama request. A successful reply is normalized. If structured JSON was requested, the gateway parses and validates it; a bad result gets one repair request to the same provider. The gateway logs the outcome and returns the normalized response. A real provider failure is logged, may put that provider into temporary backoff, and returns an error without moving to the next chat provider.

For embeddings, the caller submits text and a retrieval purpose. A profile can pin the exact expected provider, model, and width. Oversize text is rejected. With no pin, the gateway tries eligible embedders in order and proceeds to the next after a real failure. On success it records rate state, verifies a profile contract when present, logs the call, and returns the vector with its provider, model, width, latency, and failed or skipped attempts.

Preflight is a client-side journey combining both paths. It makes a small schema-constrained chat request with reasoning disabled and a sufficiently generous output allowance, then embeds a short phrase through `chunker-v1` by default. It returns both results only when both are healthy; otherwise it raises one error carrying the result of each check.

## 5. How the System Makes Decisions

Startup decides which chat providers exist from enable switches and API-key presence. Local Gemma and local Phi-4 require explicit opt-in. Provider order is read once when the module loads, while the embedding registry and order are built during application startup.

At chat time, an explicit provider or resolved profile narrows the candidates to one. Otherwise the configured order is used. Selection favors the first candidate that advertises every requested capability, fits the estimated context, and passes its in-memory rate state. An explicit selection may briefly wait for a short cooldown, for at most about thirty seconds. Once a provider is selected, success or failure ends the chat journey.

Structured validation happens only when a schema exists and the model did not instead emit tool calls. Invalid JSON or schema violations trigger exactly one repair call. Tool calls take a separate route: they are returned to the caller for execution elsewhere. Reasoning settings are applied only to model families known to support them, and some adapters retry without reasoning if the provider rejects that setting.

Embedding decides between a named provider/profile and a failover ring. A pin disables fallback. The unpinned ring skips temporarily unavailable candidates and continues after call failures. A profile then adds a final identity check, rejecting even a successful vector if the reported model or dimension violates the pin.

## 6. How the Code Actually Flows — The Execution Journey

Execution normally begins when an application server imports `main.py` and enters the FastAPI lifespan. Configuration is read from the parent directory's `.env` file. The database schema is prepared, provider objects and their in-memory state are created, and endpoints begin waiting for HTTP requests. A direct run of `main.py` starts the server on port 8107 by default. The Python client and its small command-line entry are separate entry points that send HTTP requests to that server.

When a request arrives, the HTTP framework first turns it into one of the declared request shapes. Chat then moves through normalization, optional profile resolution, size estimation, capability filtering, provider selection, adapter translation, the external call, normalization, possible structured repair, logging, and response construction. Data changes from the caller's common conversation shape into a vendor-specific payload, then back into normalized text and tool calls. The provider adapter is the main hand-off point in both directions.

The nominal streaming path returns a server-sent event response and runs its work inside a generator. In the current adapters, however, the base streaming method first waits for the full ordinary chat result and then yields the full text, so this is not true provider-token streaming. If streamed structured text is invalid, the original deltas may already have been sent before the gateway performs a repair and places corrected text in the final event. Callers must therefore treat the final event as authoritative for structured streaming.

No chat branches run in parallel. The service waits for one provider response, one optional repair response, or one embedding provider at a time. Embedding failover is sequential. The only synchronization objects are in-memory locks around provider-selection state and Gemini cache bookkeeping; the provider-selection lock is currently unused.

Requests finish after the result or error is written to SQLite and returned. The application lifespan has no explicit shutdown cleanup beyond leaving its context. Open network clients are scoped to individual calls and close themselves. The database connection helper closes every connection. What remains after shutdown is the SQLite log; usage counters, backoffs, and cache references are forgotten.

## 7. What the System Remembers

The durable memory is `gateway_v7.db`. Each row remembers when a call occurred, which provider and model handled it, whether it succeeded, latency, token and character counts, cache usage, tool-call count and dialect, reasoning use, explicit override, skipped attempts, call role, embedding width, and named profile. The code can add newer columns to an older database but does not otherwise version migrations. Corruption or accidental deletion loses history, not core call capability.

Chat rate state remembers calls and tokens in the last minute, totals for the current UTC-style epoch day, the last call time, and temporary unavailability. Embedding state remembers its own recent calls, cooldown, and escalating failure step. These memories protect upstream quotas only within one process and reset on restart.

The Gemini cache remembers a hash of model plus system text, the upstream cache name, and expiry for five minutes. It is an optimization, so losing it increases repeated input work but should not change answers. Configuration and profile tables are process-lifetime memory loaded from code and environment; changes require a restart.

## 8. What the System Talks To

The gateway talks to the Gemini, OpenAI, and Anthropic HTTP APIs for chat when their keys are configured. It talks to a local Ollama daemon for optional local chat, exact Phi-4 segmentation, and default embeddings. Gemini is also the optional embedding fallback. A provider outage becomes a chat error after selection; an unpinned embedding call may continue to its next candidate.

It reads a parent-directory `.env` file for credentials and settings, and it reads and writes `gateway_v7.db` in the project directory. It creates short-lived HTTP clients per provider request. It has no web UI, external queue, general-purpose cache server, shared rate database, tool registry, MCP connection, or agent loop.

Several historical documents point outside this repository to ingestion plans and change receipts that are not present here. Those references may exist in another project, but they cannot serve as self-contained evidence inside this codebase.

## 9. What Is Currently Built vs. What Is Not Yet Built

The current code has completed the major June cleanup recorded in `CHANGES.md`: the old V3 AI tier classifier, router pool, `auto_route` request behavior, router-decision response, old provider matrix, dashboard, help page, and router endpoint are absent. The provider registry now contains the Gemini, OpenAI, Anthropic, and opt-in Ollama families, and chat stops after one selected provider's runtime result. Focused tests confirm the one-attempt rule and provider protocol normalization.

The July additions are also built. Embedding profiles, profile logging, embedder discovery, client status calls, and real preflight are present. Gemma chat has subsequently become opt-in rather than default. The code also has a `knowledge-extraction-v1` Anthropic Sonnet chat profile, an exact optional `document-segmentation-v1` Phi-4 route with a resolution endpoint, normalized Ollama length stops, and Anthropic native structured output with schema cleaning and final gateway validation.

Some cleanup goals remain open. The README has only a short current preface; most of it still documents the deleted V3 classifier, old seven-provider pool, dashboard, `/v1/routers`, port 8101, and `auto_route`. The small generic typed-Pydantic client helper has not been added. The chat handler remains large and duplicates structured repair. `router.py` has not been renamed, and `providers.py` has not been split. There is no focused test module for rate-state edge cases or the gateway's complete structured repair paths. The package summary is stale. The optional tool-normalization layer remains because tests and the live schemas still use it; whether the surrounding harness truly needs model-emitted tool calls cannot be proven from this repository.

The cleanup handoff itself is partly stale as a task list. It still says to remove `auto_route` from the client, but the current client and schemas already lack it. It also frames the README rewrite, typed helper, handler split, possible file renames, and database-field review as future priorities. Those remaining items should be evaluated individually rather than assuming the whole list is undone.

The best reference documents are divided by date and purpose. `CHANGES.md` records the June provider reduction, classifier and UI removal, selection rule, schema removals, rate-limit changes, and endpoint surface. `CHANGES_2026-07-27_preflight_and_profiles.md` records embedding profiles, client discovery methods, preflight, test rationale, and version 0.2.0. `CHANGES_2026-07-29_phi4_segmentation.md` records the exact Phi-4 chat profile and Ollama stop normalization. `CHANGES_2026-07-29_anthropic_structured_output.md` records native Anthropic schema output and version 0.2.1. `CLEANUP_SUMMARY.md` and `AGENTS.md` record product boundaries and unfinished cleanup direction. The code remains the authority where these documents disagree.

## 10. The Current State of the Project

This is a working, compact personal gateway in the middle of a behavior-preserving cleanup. Its strongest part is the explicit boundary around provider protocols: callers get one contract, tool calls are normalized but not executed, structured JSON is validated again at the gateway, embeddings can be pinned, and operational outcomes are logged.

Its most fragile part is documentation and contract drift. The README mixes a correct current preface with hundreds of lines about a system that no longer exists. `CHANGES.md` also predates the opt-in Gemma policy and newer chat profiles, and its displayed default order still begins with Gemma while the code's default order does not. A new maintainer should begin with `AGENTS.md`, the dated change notes, and this overview, then verify claims against `main.py`, `providers.py`, and the tests. They should not use the README's V3 section to design new integrations.

Before production use, a maintainer should also understand that chat rate awareness is process-local, nominal streaming is not truly incremental at the provider level, different embedding models are not proven interchangeable merely because both return 768 numbers, and the database has only lightweight in-place migration logic. None of these issues makes the current personal gateway unusable, but each becomes important if the service is scaled, made multi-process, or trusted as a long-lived shared platform.
