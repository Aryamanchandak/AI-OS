
• This is a course workspace containing several separate projects, not one app.
  I ignored virtual environments (.venv), caches, ZIPs, PDFs, databases, and
  other generated files when rating.

   Folder           What its code does                                   Rating
  ━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━
   Lecture 3        Introductory Python/agent examples: REPL               6/10
                    interaction, async patterns, debugging, simple
                    LLM calls, and progressively more complete agent
                    loops.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Lecture 4        Small MCP/decorator exercises: defines tools with      6/10
                    decorators, exposes an example MCP server, and
                    includes a client that talks to it.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Lecture 7        A complete iterative agent: remembers context,         8/10
                    plans goals, decides tool calls, executes through
                    an MCP server, stores artifacts, and uses vector/
                    FAISS document memory. Its llm_gatewayV7 is a
                    FastAPI model router with failover, rate
                    limiting, embeddings, SQLite call history, and a
                    dashboard.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Assignment 5     Contains three related apps: Veritas, which            8/10
                    researches and verifies scientific claims with
                    citations and self-critique; a Streamlit prompt/
                    plan workbench; and scripts that synchronize/
                    evaluate prompt specifications.
  ───────────────  ───────────────────────────────────────────────────  ────────
   veritas copy     A compact duplicate/earlier copy of the Veritas        5/10
                    command-line research pipeline. It appears to be
                    a backup, not the primary maintained
                    implementation.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Assignment 8     Three substantial reasoning apps: a concurrent       8.5/10
                    DAG-based equity-comparison agent; Causal
                    Scenario Engine, which turns a “what if” into
                    evidence-backed causal scenarios; and Consequence
                    Radar, which analyzes finite news batches for
                    Indian-equity consequences.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Assignment 9     Browser-comparison agent with a four-step            8.5/10
                    browser-understanding cascade: static extraction
                    → deterministic browser controls → accessibility-
                    tree reasoning → vision. It records runs into
                    self-contained replay reports. Includes Gateway
                    V9 for chat, vision, embeddings, routing, and
                    cost tracking.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Assignment 10    Extends the agent into computer use: drives macOS      8/10
                    apps through Accessibility APIs, AppleScript
                    keyboard/mouse input, screenshots, optional
                    vision, action recording, and recovery/replay
                    logic. Also preserves browser and research
                    skills.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Lecture 11       GLC v1: a model gateway expanded into a multi-       7.5/10
                    channel system. It normalizes messaging channels
                    such as WhatsApp, adds policy/trust controls, and
                    supports speech-to-text/text-to-speech providers.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Lecture 12       Multiple copies of the GLC v2 security               6.5/10
                    assignment: gateway deployment via Modal plus
                    intentional security flaws/reference versions
                    used for auditing and fixes. telegram_adapter.py
                    is a smaller standalone integration.
  ───────────────  ───────────────────────────────────────────────────  ────────
   glc_v2_fixed     The fuller Session 12 gateway reference: model/      7.5/10
                    provider routing, cost ledger, channel envelopes,
                    channel adapters, voice routing, security
                    policies, tests, and Modal deployment wrapper.
                    Despite the name, the README says it
                    intentionally retains flaws for the security
                    exercise.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Assignment 13    Two core services: glc_v3, the credential-owning       9/10
                    gateway for models/channels/voice/security; and
                    S13Code, a standalone runtime with live task
                    graphs, durable semantic memory, document
                    indexing, and Agent-to-Agent (A2A) HTTP/gRPC
                    interoperability. S13Proof verifies it with
                    deterministic and live benchmarks.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Assignment 14    No implementation source found; likely assignment       N/A
                    material only.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Assignment 15    The most mature evolution: S15Code is an agent         9/10
                    runtime with constrained planning, durable graph
                    events, memory, A2A, human approval, budget
                    enforcement, and telemetry. glc_v4 adds
                    accounting/billing principals and call-allowance
                    policy to the gateway.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Assignment 16    Markdown/lecture material only; no source code          N/A
                    found.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Assignment 17    Markdown/lecture material only; no source code          N/A
                    found.
  ───────────────  ───────────────────────────────────────────────────  ────────
   Multi Channel    “Switchboard,” a planned human-in-the-loop inbox     6.5/10
                    assistant. It has useful Pydantic models,
                    configuration, storage, and channel interfaces,
                    but the design explicitly says it is not fully
                    built yet.

  Overall: this is strong work, especially from Assignments 8 onward. The best
  qualities are typed data contracts, clear separation between gateway/runtime/
  tool layers, meaningful tests, explicit cost tracking, and safety boundaries.
  The main thing holding the workspace back is duplication: multiple generations
  of GLC and agent runtimes coexist, making it harder to know which folders are
  current.
