# Gateway YAGNI Review: Answers to Your Comments

> Historical review from before the shrink. For current scope and status, see
> [Gateway status](plans/README.md).

As of 2026-10-18 · Follows `docs/yagni-review.md` · Nothing in the code has been changed

You left 22 comments. This document answers each one in the order it appears in the review. Your answers also change three of the review's recommendations. Those changes come first.

---

## What your answers change

| Change                                                                        | Before                                                                             | Now                                                                                                              | Why                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **The single call log**                                                       | Tier 3 said the audit database should be the one place every LLM call is recorded. | The **ledger** should be the one call log. The audit database should go instead.                                 | I checked both table layouts. The audit table was designed for the old channels work: its columns are `channel`, `trust_level` and `policy_verdict`, and each LLM call is squeezed into one JSON text field. The ledger has a proper column for each fact about a call: provider, model, tokens, cost, agent, session and so on. The review had this the wrong way round. |
| **Gemini**                                                                    | Tier 5 asked only about Gemini's context cache and the 10 keys.                    | Remove the **whole Gemini provider**: the adapter, the context cache, the 10 keys and the Gemini tests.          | You said you won't use Gemini at all.                                                                                                                                                                                                                                                                                                                                     |
| `batch: true` **is a bug, not just unused [THIS NEEDS TO BE BUILT PROPERLY]** | Tier 5 called the field "half-used".                                               | A request marked `batch: true` is **recorded at the cheaper batch price but sent as a normal, full-price call.** | Your budget figures under-report real spend for any call that sets it. This is the strongest reason to fix it, whatever we decide about batching.                                                                                                                                                                                                                         |

---

## Comments on the summary table

### Tier 1: "We can safely get rid of this"

Agreed, with one adjustment. Your later comment on Tier 1 is right that some items are unfinished features, not junk. The split is in the Tier 1 section below. About half the items should be finished and used, not deleted.

### Tier 2: "Why do we have this in the first place?"

The gateway was moved over from your older system, "GLC", in Plans 01–07 (September 2026). That move kept every old web address (URL) and every old response layout, so that whatever already called the old system wouldn't break. Some old features weren't brought across, such as the router that picked a model automatically. Their URLs were still kept, and they now return placeholder answers so callers get a reply instead of an error.

So these routes are leftovers from that move. They only matter if something still calls them. The likely caller is the shell, your web UI in `../shell`. I haven't looked there, because I'm keeping to the gateway folder. **If you want me to check, say so and I'll search** `../shell` **for these URLs. I'll only read, not change anything.**

### Tier 3: "Need to look into, can't delete willy nilly"

Agreed. Tier 3 deletes nothing. It **merges** code, so that each job is done in one place instead of several. Each merge would:

1. Add a test showing how things behave today.
2. Merge the code.
3. Run the same test to show nothing changed.

The call-log merge is also the one I got wrong, as explained at the top. The other merges are low-risk: the YAML loading, the two copies of `validate_host` and the two ways of opening SQLite. "YAML" is the plain-text format of your config files.

### Tier 4: "We need tests, right?"

Yes, and nothing here removes tests for code that stays. The rule I'm following:

- **A test goes only when the code it tests goes.** A test for a deleted route would fail for no useful reason.
- **Code that stays keeps its tests, and it gets more.** The golden set is the main addition. It's a short list of real requests with known good answers, run after every trunk change. Your notes say it doesn't exist yet.
- **Your rules require your explicit OK for every test file I delete.** I'll list each one in the plan before touching it.

Tier 4 is about features that belong outside the gateway, such as serving the shell's web files. When one moves out, its tests move or go with it.

### Tier 5: "What does this mean? … the code needs to work end to end to be usable"

"End to end" means one real request goes into the gateway, reaches Claude or GPT, and a correct answer comes back. Along the way, the call is checked against the budget, recorded in the call log, and costed correctly. Your notes say this has **never been done** with this gateway.

Tier 5 lists extras built on top of that unproven path: caching, five-level budgets, streaming, batch and so on. My point matches yours: **the code is no use until the basic path works.** Every extra is more code that could hide the bug stopping it. The plan:

1. Cut the extras you don't need now.
2. Prove the basic path with the golden set.
3. Add extras back one at a time, each one checked against the golden set.

Your answers on each Tier 5 item are applied in the Tier 5 section below.

### Tier 6: "This is interesting, what do you propose here?"

See the Tier 6 section at the end. In short: replace the hand-written provider code with Mozilla's **any-llm** library, behind one adapter file.

---

## Comments on "What was reviewed"

### Platform: "What does this do?"

`platform/` is the shared plumbing the LLM code stands on. It's about 700 lines in five parts:

| Part | One-line job | Verdict |
| --- | --- | --- |
| `configuration/` | Works out file paths, such as where the databases and config files live, and loads settings. | Keep the paths. The `GatewaySettings` half is dead (Tier 1). |
| `service_registry/` | A checked list of the host and port for three services. | Probably shrinks to one value once Tier 4 is decided. |
| `database/` | One shared helper for opening SQLite, the single-file database the gateway uses. | Keep. |
| `networking/` | One shared HTTP client, the code that makes web requests to OpenAI, Anthropic and others. | Keep for now. With any-llm it mostly goes, because the library makes its own requests. |
| `observability/` | Records a timeline of each request ("tracing") and keeps recent ones in memory to show on a page. | Keep the tracing. Drop the in-memory copy (Tier 6). |

### App wiring: "Why do we need this?"

The gateway is a FastAPI app. FastAPI is the web framework: the library that turns Python functions into URLs. Something has to:

- create the app and attach every route to it,
- check the access token on each request,
- open the databases and build the LLM service at startup, and close them at shutdown.

`app/` does those jobs. Every FastAPI project has this layer, so it can't be deleted. It can get smaller: about a third of it supports Tier 4 items (old `/v1` URLs, serving the shell, `/healthz`, `/dashboard`).

---

## Comments on "CLAUDE.md rules already broken"

### "OpenTelemetry is for what?"

OpenTelemetry ("OTel") is the industry-standard library for **tracing**. For each request, it records a timeline of every step and how long each took: budget check, provider call, cost calculation. When a call is slow or fails, the trace shows which step was to blame. It's plumbing, so using a library is right.

What's wrong today:

- **It's imported in several files.** Your rule is one adapter file per library.
- **The gateway keeps its own in-memory copy of recent traces** (`capture.py`, ~230 lines) to show on its own page. That copy is lost on restart.

The usual setup is a separate trace viewer that reads OTel data. Arize Phoenix and Langfuse are both free to run locally. **Proposal:** keep OTel, put it behind one adapter file and delete the in-memory copy. Then pick a viewer when you first need to debug a trace, not before.

### "Good to have it tho, not sure about having 32"

The 32 is a cap on how many provider calls can run at the same time. A cap only limits things, so it isn't the problem. The problem is `/chat/batch`, which fires off many calls at once on purpose.

- **Keep a cap.** It's cheap protection against an agent stuck in a loop running up your bill. Lower it to something like 4 and move it into config, so you can change it without editing code.
- **Remove** `/chat/batch`**.** The real batching you asked for is a different thing; see the Tier 5 section.

---

## Comments on Tier 1

### Overall: "These are useful features. Why aren't they being used? Which are truly not required?"

Fair challenge. Sorted:

**Finish and use these (5 items):**

| Item | What it was for | Proposal |
| --- | --- | --- |
| `CallLedger` | A detailed record of every LLM call: tokens, cost, agent, session and more. It was built and opened at startup, but the step that writes to it was never connected. | Make it **the** call log (see the correction at the top). Connect the write step, and have `/calls` and `/cost/`* read from it instead of from memory, which is lost on restart. Trim the columns for features that don't exist: `router_decision`, `escalations`, `tier`, `cache_*`. |
| `ChatResponse`, `EmbedResponse`, `ToolCall` | Typed descriptions of what `/chat` and `/embed` return. | **Yes, these should be used.** Today the routes return loose dictionaries, so nothing checks the reply's shape and the contract file can't describe it. Attaching them to the routes makes the reply a checked promise to every agent. This is your trunk's "contracts" job. |
| `AuditStore.query` | Reads the log back, filtered by session. | The idea is right, but it belongs on the ledger. It moves with the call-log merge. |
| `GLCPaths.load_mapping` | Reads a YAML file and checks it's a list of key–value settings. If not, it raises a clear error. | Six other files each have their own copy of this. Make this one the **single** version, in the `config.py` adapter (Tier 3), and delete the six copies instead. |
| `content_has_image` | Answers one question: "does this message contain an image?" | Useful for refusing to send an image to a model that can't see images. Keep it if the image check is built; see the images answer below. |

**Truly not required (delete):**

| Item | Why |
| --- | --- |
| `GatewaySettings` + `gateway.yaml` | Repeats settings that `services.yaml` already holds. Nothing reads it. |
| `RouterDecision` | Describes the output of the auto-router, which doesn't exist. |
| `failure_policy = "closed"` | Only a label. The behaviour it describes is real: if writing the log fails, the request fails. That behaviour stays. Nothing reads the label. |
| `assert_safe_url` | A one-line wrapper around the real SSRF check. It goes with the SSRF decision below. |
| `Usage` | An exact duplicate of `ProviderUsage`. |
| Budget `projection`, `alerts`, `load_overrides` | Settings that are read and then ignored. Spend alerts ("warn me at 80%") are a good idea. Build them properly when you want them, rather than keep a stub that does nothing. |
| `max_retries`, `max_concurrency` arguments | Retries come from the library after Tier 6. The cap moves into config, as above. |
| `thinks_by_default` + "dead in practice" branches | Workarounds inside the hand-written provider code. They go with Tier 6. |
| Stale "Plans 02, 04–06" docstring | Describes plans that are finished. |

### `ToolCall`: "This isn't good is it, this should be used?"

Yes, it should. See "Finish and use" above.

### `failure_policy`: "Why?"

It's a label written for readers of the old code. Nothing in the program checks it. The real behaviour, where the request fails if the log write fails, comes from the code itself and stays.

### `assert_safe_url`: "Why?"

It's a shortcut someone added for convenience and never used. Whether the SSRF code stays at all depends on the images question below.

### `GLCPaths.load_mapping`: "What does this do?"

It opens a YAML config file, checks it holds a list of `name: value` settings and gives a clear error if not. Six other places do the same job, each with its own copy. This copy should become the only one.

### `content_has_image`: "Why are we looking at images here? Inbound is not the purview of this gateway"

Right: the gateway shouldn't go out and **fetch** content. Images reach it only because an agent sends one **inside a chat request** for Claude or GPT to read, for example a scanned annual-report page. Forwarding that image to the LLM is squarely the gateway's job, and `content_has_image` only looks inside that request.

The part that **is** outside the gateway's job is `security/ssrf.py`. When a caller sends an image *link* instead of the image itself, the gateway downloads it from the internet. That's inbound fetching, it's risky, and it relies on private internals of the `httpx` web library. "SSRF" is the attack where someone tricks a server into fetching from addresses it shouldn't.

**Proposal:** callers send the image itself as a `data:` URL, meaning the image bytes written into the request. Whichever leaf agent downloaded the image already has it. The gateway never downloads anything, and `ssrf.py` (~145 lines) goes. **I need your yes on this.**

### `python-dotenv`: "Useful features … why aren't they being used?"

`python-dotenv` stays. It's how API keys will be loaded from `.env`. The step that loads them hasn't been written yet, which is one reason the gateway has never run end to end.

---

## Comments on Tier 2

### Route-by-route verdict

| Route | Proposal |
| --- | --- |
| `GET /routers` | Delete. Routing doesn't exist. |
| `GET /telemetry` | Delete. It's a hard-coded answer. |
| `GET /embedders` | Fix. Report the real embedding model and its real size, instead of the hard-coded 768. |
| `status()` | Fix. Report only providers that have a key set. |
| `providers()` | Fix. Drop the always-empty `shortcuts` and `limits` fields. |

All of these wait on the `../shell` check described above.

### `contracts/openapi.json`: "Why is this?"

`contracts/openapi.json` is the gateway's **written promise**: every URL, what it accepts and what it returns. FastAPI generates it from the code. A saved copy is kept so that:

1. **Agents (leaves) have a fixed contract to code against.** Your CLAUDE.md lists "MCP contracts" as a trunk job, and this file is the same idea for the HTTP routes.
2. **Accidental changes get caught.** A test regenerates the description and compares it with the saved copy. If a code change quietly alters a route, the test fails. Then you either fix the code or confirm the change on purpose by running `python scripts/export_openapi.py`.

So a failing contract test asks "did you mean to change the promise?" It isn't a bug.

---

## Comments on Tier 5, applied

| Feature | Your answer | Proposal |
| --- | --- | --- |
| `/vision` | "No, we need to process images." | Agreed that images must work, and they will. Images already work through `/chat`, and `/vision` is a second URL that passes them to `/chat`. I'd still remove `/vision` and keep `/chat`, so agents have one way to send an image. **Your call.** If you'd rather keep both, I'll leave it. |
| Unused request fields | "I don't know what this does." | `auto_route` lets the gateway pick a model for you. `cost_quality_tradeoff` is a "cheap ↔ best" dial for that picking. `escalate` retries with a stronger model if the first answer is weak. None of these is built, so all three go. `batch` is the bug described at the top: remove it now, and bring it back only as part of real batching. |
| Batching section | "We should build a batching section … send and store batches and receive them back." | Good idea. Anthropic, OpenAI and Together all offer batch services: submit many requests at once, get results within about 24 hours, at roughly half price. Mozilla's any-llm supports batch for all three. Two notes. (1) **Rule flag:** this is a new feature, and your rules say to flag new features until one request works end to end. It goes **after** the golden set. (2) "Receive them back" needs something to check every few minutes whether a batch has finished. Your rules say never to write scheduling code yourself, so that checking will need a scheduling library. That will be a dependency decision when we get there. |
| Gemini context cache | "We won't be using Gemini at all." | Remove all of Gemini (see the top). |
| Up to 10 Gemini keys | "No." | Goes with Gemini. |
| Which providers | "Just Claude and GPT for now, and Together.ai." | Remove Groq, Cerebras, NVIDIA, OpenRouter and GitHub. **Together isn't in the gateway yet.** It uses the same request format as OpenAI, so adding it is one config line today, and it's built in with any-llm. **Two questions for you below:** Ollama, and the three-tier naming. |
| Streaming | "No." | Remove the streaming path (~150 lines) and `test_llm_streaming.py`. That test file needs your explicit OK. |
| Semantic cache | (no comment) | Still needs your answer: have you ever turned it on? |
| Five-dimension budgets | (no comment) | Still needs your answer: are agent + session enough? |

---

## Tier 6 proposal: Mozilla's any-llm

**What it is.** `any-llm` (package name `any-llm-sdk`, Apache 2.0 licence, from mozilla.ai) is a Python library that calls many LLM providers through one interface. It needs Python 3.11 or later; the gateway already requires that. Unlike some alternatives, it uses each provider's **official** library underneath (Anthropic's own, OpenAI's own), so behaviour matches the providers' documentation.

**What its documentation says it supports, for your three providers** (provider table at docs.mozilla.ai/any-llm/providers, checked today):

| | Chat | Streaming | Images | Embeddings | Batch |
| --- | --- | --- | --- | --- | --- |
| Anthropic | ✅ | ✅ | ✅ | ❌ | ✅ |
| OpenAI | ✅ | ✅ | ✅ | ✅ | ✅ |
| Together | ✅ | ✅ | ✅ | ✅ | ✅ |

**What it replaces:** the five hand-written provider adapters, the capability guesses, both schema cleaners and the Ollama tool workaround. That's about 1,000 lines, replaced by one `llm.py` adapter that should be well under your 200-line limit.

**What it doesn't replace, as far as I could confirm:**

- **Retries.** Its main page doesn't mention retries. Anthropic's and OpenAI's official libraries retry failed calls by themselves, but I haven't confirmed that any-llm passes that through. **I'll check its documentation for the pinned version before relying on it.** If it doesn't, the `tenacity` library is the fallback, not hand-written code.
- **Pricing and budgets.** These aren't part of the any-llm library. Mozilla offers them in a separate full gateway product called Otari. That's a much bigger decision, because it would replace your trunk gateway, not just the provider code. I haven't evaluated it. Keep your own `pricing.py` and budget code for now.

**Ladder step:** "replace", the last rung. That's justified here because the hand-written code repeats plumbing the library provides.

**Version note:** the newest release is 1.37.0, published 2026-10-16, two days ago. Pin a release that has been out for at least a few weeks, and record it in `DEPENDENCIES.md` with its job, version, why it was chosen and how we'd move off it.

**Order:**

1. Do Tiers 1–2 and the Tier 5 removals (Gemini, the free-tier providers, streaming). These shrink the code first.
2. Write the `.env` loader. Get one Claude request working end to end through the current code. Record 3–5 real requests as the golden set.
3. Swap the provider code for any-llm behind `llm.py`. The golden set must still pass.
4. Add Together. Then add batching as its own planned feature.

The golden set comes before the swap so we can prove the swap changed nothing.

---

## Questions still open

1. **Shell check:** may I read (not change) `../shell` to see whether it calls `/routers`, `/telemetry`, `/v1/...`, `/healthz` or `/dashboard`?
2. **Images:** can every caller send images as `data:` URLs, so the gateway never downloads anything and `ssrf.py` can go?
3. `/vision`**:** keep it as a second URL, or send everything through `/chat`?
4. **Ollama (local models):** you didn't mention it, but **embeddings run on Ollama today** (`nomic-embed-text` in `config/profiles.yaml`). Anthropic has no embeddings service. Keep Ollama for embeddings, or move embeddings to OpenAI or Together?
5. **Model tiers:** keep the three named tiers each for OpenAI and Anthropic (`openai-cheap/mini/pro`, `anthropic-haiku/sonnet/opus`), or one entry per provider with the model chosen per request?
6. **Semantic cache:** ever turned it on? If not, it goes (~400 lines).
7. **Budgets:** are agent + session enough?
8. **Test files:** may I delete `test_llm_streaming.py` along with streaming, and the Gemini tests in `test_llm_providers.py` along with Gemini?

---

## Commit this document

Run these from the `gateway` folder:

```
git add docs/yagni-review.md docs/yagni-review-followup.md   # stage the review with your comments, plus this answer doc
git commit -m "Add answers to YAGNI review comments"          # save a snapshot of those two files
```

The first command stages only these two docs, not the other uncommitted changes in your folder.
