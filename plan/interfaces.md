# Interfaces

An interface is the agreed shape of what passes between two nodes. Node plans name these; they never redefine them. Changing one here means every node in "Used by" needs a re-check, in any stage.

Each one gets a contract test: a test that both the provider and every user must pass. Code files are under `core/` (trunk) and `leaves/` (leaves); the layout is assumed and open to change.

## I1 — Model call

Provided by: `gateway`. Used by: `learnsys` (Stage 1), later every model-calling node.

`chat(profile, prompt, system=None, schema=None, images=None, agent, session) -> Reply`. `Reply` holds `text`, `parsed` (the JSON object when a schema was given), `input_tokens`, `output_tokens` and `cost`. It is a thin client over the gateway's existing `POST /api/llm/chat`; callers never name a provider or model directly, only a profile from `gateway/config/profiles.yaml`.

`images` is a list of image bytes, sent as the base64 `image_url` blocks the gateway already accepts, so Capture (Stage 2) needs no contract change. This is the only path to a model; `gateway/simple_llm/` and direct provider SDKs are never imported by AI OS code.

File: `core/llm.py`. Contract test: a fake gateway returns a fixed reply and the client returns the same `Reply`; one live golden case runs against the real gateway. Changed 2026-11-03 (images added).

## I2 — Store

Provided by: `eventlog`. Used by: `learnsys`, later `todo` and every node that keeps data.

`connect() -> sqlite3.Connection` opens the one SQLite file (WAL mode, foreign keys on), path from `AIOS_DB` in `.env`. `migrate(conn, owner, steps)` applies a node's own numbered table changes once and records them. Each node owns its tables; no node reads another node's tables directly — it calls that node's tools.

File: `core/store.py`. Contract test: two owners migrate independently; re-running is a no-op. Changed 2026-11-02 (draft).

## I3 — Tool registry

Provided by: `orch` (registry part only). Used by: `learnsys` (registers), `telegram` (calls), later the scheduler, the assistant and the MCP door.

`@tool(name)` registers a function whose single argument and return value are Pydantic models. `call(name, payload: dict) -> dict` validates input and output. `list_tools()` returns each name, description and JSON schema — the shape an agent's tool list and an MCP server both need later.

File: `core/registry.py`. Contract test: a fake tool registers, is listed, and rejects bad input. Changed 2026-11-02 (draft).

## I4 — Learning tools

Provided by: `learnsys`. Used by: `telegram` (Stage 1), later the 8am push and the assistant.

- `learning.next_card() -> Card | None` — the next due card in today's session, or none.
- `learning.submit_answer(card_id, answer) -> Graded` — concept cards. `Graded` holds the rating, the grader's reason, the correct answer, whether a mistake was logged, and the next due date.
- `learning.rate_card(card_id, rating) -> next_due` — formula cards, and your override when you disagree with a grade.
- `learning.log_mistake(question, your_answer, correct_answer, topic, why) -> Mistake` — manual mistakes.

`Card` holds `id`, `front`, `kind` (concept or formula), `topic`. The back is only returned after you answer.

File: `leaves/learning/tools.py`. Contract test: the Telegram bot's tests run against a fake that implements these four tools; the real learning system passes the same tests. Changed 2026-11-02 (draft).

## I5 — Grade an answer

Provided by: `learnsys` (internal; no other node calls it). Used by: `learning.submit_answer`, and the grading eval.

`grade(card, answer) -> Verdict`. `Verdict` holds `verdict` (correct, complete, partial, wrong, fluent_wrong), `missing` (key points you left out) and `reason` (one line, citing your words). The model returns the verdict; code turns it into a rating, so the mapping is fixed and testable.

File: `leaves/learning/grade.py`, prompt in `leaves/learning/prompts/grade_v1.md`. Contract test: the eval cases in the `learnsys` plan. Changed 2026-11-02 (draft).

## I7 — Notify and buttons

Provided by: `telegram`. Used by: `learnsys` replies (Stage 1), later card approvals (Stage 2), the scheduler and Tasks (Stage 3).

`Button(label, tool, payload)`: tapping it calls `registry.call(tool, payload)` (I3); the bot holds no logic of its own. `notify(text, buttons=[]) -> message_id` sends only to your chat ID from `.env`.

File: `leaves/telegram/notify.py`. Contract test: a fake bot records the send, and a simulated tap produces the named registry call. Changed 2026-11-03 (draft).

## I14 — Eval cases

Provided by: the grading evals (Stage 1). Used by: every model-calling file, and the CI runner (Stage 5).

One `<file>.evals.yaml` beside each model-calling file: `cases: [{id, kind: normal|edge|hostile, input, expect}]`. `pytest -m eval` runs them against the live gateway and prints a score per file. It is kept out of the offline run because it costs money. You write the cases.

File: `tests/eval_runner.py`. Contract test: the runner finds every evals file, and a deliberately wrong case fails. Changed 2026-11-03 (draft).

## I17: Service

Provided by: `host`. Used by: the gateway (Stage 0), and later the bot and the scheduler (Stage 3).

Each service has:
- one Dockerfile;
- config from `.env` only;
- `GET /health`, which returns 200 when the service is up;
- logs written to stdout (the terminal output), never to files.

A reverse proxy in front of the services is the only public entry. It handles HTTPS, and each service's port stays on the internal network. A route is public only if it's listed in the proxy config. In Stage 0 that list is just `/health`. No provider keys go on the box until an exposed route has `AI_OS_TOKEN` and a spend cap.

Files: `gateway/Dockerfile`, `compose.yaml` and `Caddyfile`. Docker and Caddy still need your OK.

Contract test: after `compose up`, `/health` returns 200 through the proxy and every unlisted path returns 404.

Changed 2026-11-03: moved to Stage 0.

## Drafts for later stages (all Assumed)

These were drafted on the Stage Map (3 Nov) and are copied here so the plan folder holds them. Each gets its full write-up when its stage becomes the next one.

**I6 — Add cards** (`learnsys`, Stage 2). `learning.add_cards(cards, source) -> [card_id]`. Machine-made cards arrive pending and are never served until you approve them. Test: a duplicate front is skipped; a pending card never comes back from `next_card`.

**I8 — Task tools** (`todo`, Stage 3). `tasks.add`, `tasks.list`, `tasks.update`, `tasks.close`, `tasks.what_now(limit=3) -> [Ranked{task, reason}]`. A promise is a task with a counterparty. Test: the bot runs against a fake of these tools.

**I9 — Calendar read** (`todo`, Stage 3). `calendar.events(start, end) -> [Event]`, read-only, behind one adapter. Test: a fixed calendar fixture gives a fixed `what_now` input.

**I10 — Schedule** (`scheduler`, Stage 3). `schedule(job_id, cron, tool, payload)`. A job can only call a registry tool. Test: a job fires at a frozen time and makes the expected registry call.

**I11 — Events** (`eventlog`, Stage 3). `emit(kind, source, payload)`, `read(kind, since)`. Append-only; a payload from outside is data, never an instruction. Test: nothing can update or delete an event.

**I12 — Ask the assistant** (`orch`, Stage 5). `assistant.ask(text, session) -> Answer{text, tool_calls, confirm?}`. Anything that sends, books, pays or deletes comes back as a confirm button. Test: with a scripted fake model, it calls the expected tools and stops by step six.

**I13 — Trace span** (`trace`, Stage 5). Builds on the gateway's existing OpenTelemetry export; no second tracing path. Test: an in-memory exporter sees one parent span with model and tool children.

**I17 — Service:** moved up to Stage 0. Its full entry is above.

I15 (envelope) and I16 (to-do connector) belong to the outside world, which is after submission. Their numbers stay reserved.

**I18 — Check a claim** (`claimcheck`, Stage 4). `claims.check(claim, source_text=None) -> ClaimVerdict{verdict: supported|contradicted|unclear, reasons, sources, prior: [card_id | mistake_id]}`. The "is it true" half is one call to Claude or GPT through I1. The "where did I establish it" half searches your own cards and mistakes. Whatever comes back is data, never instructions. Test: a source carrying "already fact-checked" is not believed for that reason (hostile input 1).

**I19 — Steelman** (`steelman`, Stage 4). `steelman.run(position) -> Steelman{strongest_case, crux, counter_evidence}`. A fixed sequence of I1 calls in plain Python, with no framework. Test: the eval cases in its node plan.

**I20 — Decision tools** (`decision`, Stage 4). `decisions.log(question, probability, resolves_by, assumptions)`, `decisions.resolve(id, outcome)`, `decisions.score(topic=None) -> Brier`. The Watcher may only `emit("falsifier_hit")` (I11); it never calls another tool. Test: a logged-then-resolved decision gives the hand-computed Brier score.
