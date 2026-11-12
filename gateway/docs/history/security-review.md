# Gateway security review

Review date: 18 October 2026  
Scope: `src/gateway` — 67 Python files and 23 README files, excluding generated interpreter files.

This report records security concerns found through source inspection and isolated local probes. It does not apply fixes. The application code was not changed during the review. Deployment configuration, reverse proxies, network reachability, and dependency vulnerabilities were not comprehensively assessed.

## Priority overview

| ID | Severity | Concern |
| --- | --- | --- |
| S1 | Critical | Legacy LLM APIs bypass bearer authentication. |
| S2 | High | The frontend fallback can serve files outside its directory when enabled. |
| S3 | High | Response-schema references can trigger internal-network requests. |
| S4 | High | Caller-controlled identity undermines budgets and tenant isolation. |
| S5 | High | Streaming and embedding work can escape spending accounting. |
| S6 | High | Chat budget reservations can underestimate actual spending. |
| S7 | Medium | Semantic cache matching omits important conversation and image context. |
| S8 | Medium | Raw upstream errors can expose sensitive information. |
| S9 | Medium | Incomplete workload limits create denial-of-service risks. |
| S10 | Medium, network-dependent | Image URL validation accepts non-public shared address space. |

Severity assumes an attacker can reach the affected interface. Loopback binding or upstream access controls can reduce exposure but do not fix the application defects. Multi-user isolation concerns matter particularly if the gateway is shared by callers with different trust levels.

## S1 — Legacy APIs bypass authentication

**Severity:** Critical  
**Evidence:** Reproduced with local HTTP requests using a stub service.

**Affected code:**

- [`app/middleware.py:15`](../src/gateway/app/middleware.py#L15): authentication applies to `/api/`, documentation paths, and selected legacy observability paths.
- [`llm/api/routes.py:191`](../src/gateway/llm/api/routes.py#L191): the complete LLM router is also registered under `/v1`.

An unauthenticated request to `/api/llm/providers` returned HTTP 401, while `/v1/providers` returned HTTP 200. The same legacy router includes chat, embeddings, usage history, budget modification, and cache purging. Those routes are outside the middleware's protected legacy paths.

**Potential impact:** Anyone able to reach the gateway can access legacy LLM operations without the configured token, consume provider resources, read operational information, and modify runtime budget overrides or purge cached responses.

**Proposed remediation:** Authenticate both canonical and legacy routers consistently. Prefer authentication attached to protected routers or a default-deny API policy, so new aliases cannot silently bypass it. Test every registered API alias with missing, incorrect, and correct credentials.

## S2 — Frontend file traversal

**Severity:** High  
**Evidence:** Reproduced locally after substituting an existing directory for `SHELL_DIST` in process memory. No filesystem changes were required.

**Affected code:** [`app/main.py:120`](../src/gateway/app/main.py#L120).

The shell fallback constructs `SHELL_DIST / route` and serves an existing file without verifying that the resolved file remains inside `SHELL_DIST`. An encoded traversal returned the repository's `pyproject.toml` in the local probe.

**Exposure condition:** The fallback is registered only when the shell distribution directory exists. The probe demonstrated the handler defect, not that a deployed instance currently exposes a particular sensitive file.

**Potential impact:** Unauthenticated reads of files accessible to the gateway process, potentially including configuration, credentials, source code, or databases, depending on filesystem permissions and path reachability.

**Proposed remediation:** Resolve the requested path and require it to remain inside the resolved distribution root, including after symlink resolution. Reject traversal and absolute paths. Consider serving existing frontend files through a containment-enforcing static-file implementation, with a separate navigation fallback.

## S3 — Schema references bypass image SSRF protection

**Severity:** High  
**Evidence:** The installed JSON Schema validator attempted to retrieve a loopback URL supplied through `$ref`. The retrieval was intercepted with a mock; no internal-network request was sent.

**Affected code:** [`llm/orchestration/structured_output.py:15`](../src/gateway/llm/orchestration/structured_output.py#L15).

The gateway accepts caller-controlled response schemas and constructs `Draft202012Validator(schema)` without an explicit retrieval policy. In the reviewed environment, default reference resolution can retrieve remote schemas. This path does not use the DNS-pinned image fetcher in `security/ssrf.py`.

**Potential impact:** Server-side requests to internal services or other disallowed destinations, blocking network activity during validation, and potentially sensitive error disclosure. End-to-end exploitation also depends on the selected provider accepting the schema and returning output that reaches validation.

**Proposed remediation:** Supply an explicit schema registry that refuses external retrieval. Allow local references only, or pre-register approved schemas without network access. Check schema validity and reference policy before contacting a provider. Bound reference resolution and validation work.

**Reference:** [Official jsonschema validator implementation and remote-retrieval warning](https://python-jsonschema.readthedocs.io/en/v4.25.1/_modules/jsonschema/validators/). The finding was verified against the local environment; library behavior may vary by version.

## S4 — Untrusted identity controls budgets and cache scope

**Severity:** High  
**Evidence:** Source tracing and an isolated budget-controller probe.

**Affected code:**

- [`llm/economics/meter.py:18`](../src/gateway/llm/economics/meter.py#L18): attribution is copied from request fields.
- [`llm/economics/budget.py:118`](../src/gateway/llm/economics/budget.py#L118): requests without matching principal policies are allowed.
- [`llm/cache/__init__.py:159`](../src/gateway/llm/cache/__init__.py#L159): cache scope is derived from supplied principal values.

Tenant, project, user, agent, and session values are optional caller input rather than authenticated identity. A probe with a zero-dollar policy for a tenant still admitted a request that omitted tenant identity. Callers can also choose the tenant value used for cache lookup.

**Potential impact:** Budget bypass by omission or impersonation, misleading audit attribution, and cross-caller cache access or poisoning where tenant scope is expected to provide isolation. The shared bearer token also grants ordinary calls and budget administration the same authority.

**Proposed remediation:** Resolve identity from authenticated credentials, require identity where policy depends on it, and reject unauthorized identity overrides. Use that verified identity for budget checks, cache scope, and audit records. Separate administrative permissions from ordinary LLM access.

## S5 — Paid work escapes accounting

**Severity:** High  
**Evidence:** Mocked streaming reproduction and source tracing of embedding execution.

**Affected code:**

- [`llm/providers/openai_compatible/__init__.py:107`](../src/gateway/llm/providers/openai_compatible/__init__.py#L107): streaming does not accumulate final usage or a completed provider result.
- [`llm/orchestration/finalization.py:18`](../src/gateway/llm/orchestration/finalization.py#L18): missing results lead to zero cost and released reservations.
- [`llm/service.py:92`](../src/gateway/llm/service.py#L92): embeddings have no budget admission and record zero monetary cost.

A mocked compatible-provider stream included token usage, but its result sink retained only the model name. Finalization without a provider result produced zero cost and reconciled with `count=False`. Direct embedding calls bypass chat-style budget enforcement, and internal semantic-cache embeddings use `record=False`.

**Potential impact:** Repeated work can consume real provider resources without reducing the recorded spending allowance. Usage reports and audit records understate costs. Interrupted buffered calls can also lack a completed result despite potential upstream charges.

**Proposed remediation:** Accumulate streamed usage and finalize a provider result. Define conservative handling for interrupted calls or unknown usage. Admit and price embedding work, including cache embeddings, against the verified caller's budget. Reconcile vendor billing where immediate usage is unavailable.

## S6 — Reservations are not a reliable spending ceiling

**Severity:** High  
**Evidence:** Source tracing and an isolated pricing probe.

**Affected code:**

- [`llm/orchestration/budget.py:16`](../src/gateway/llm/orchestration/budget.py#L16): projections use the request's `batch` flag.
- [`llm/economics/pricing.py:58`](../src/gateway/llm/economics/pricing.py#L58): batch multipliers reduce projected and recorded cost.
- [`llm/orchestration/normalization.py:35`](../src/gateway/llm/orchestration/normalization.py#L35): token estimation excludes images and tool schemas.
- [`llm/orchestration/structured_output.py:22`](../src/gateway/llm/orchestration/structured_output.py#L22): repair adds a provider call without another reservation.

Setting `batch=True` changes accounting even though adapters still submit ordinary requests. A synthetic pricing configuration demonstrated a 50% accounting discount solely from this flag. Actual discount size depends on configuration. Structured-output repair can consume an additional input/output allocation, while the initial reservation covers only one estimated call.

**Potential impact:** Real spending can exceed the allowance represented by reservations. Recorded spending can also be lower than the vendor's charge when batch discounts are asserted without actual batch submission.

**Proposed remediation:** Derive pricing eligibility from the actual submission mode. Include all billable inputs in estimates, reserve repair capacity or obtain a second admission, and treat uncertain usage conservatively. Validate configured prices and multipliers as finite, nonnegative numbers.

## S7 — Semantic cache omits request context

**Severity:** Medium  
**Evidence:** Reproduced identical cache inputs for different message structures.

**Affected code:**

- [`llm/orchestration/normalization.py:35`](../src/gateway/llm/orchestration/normalization.py#L35).
- [`llm/orchestration/cache_lookup.py:9`](../src/gateway/llm/orchestration/cache_lookup.py#L9).

Message text is concatenated without preserving roles or boundaries. Images are omitted from the text used for semantic matching. For example, two turns containing `Review this image` and `A` generated the same cache input as one user turn containing `Review this imageA`, with otherwise equivalent fields. Different images paired with identical text also lack an image-specific distinction.

**Potential impact:** Incorrect or attacker-influenced cached answers may be returned for materially different requests. Combined with S4, caller-controlled scope increases cross-caller risks. Semantic caching is opt-in by default, so this concern applies when caching is enabled for a request.

**Proposed remediation:** Include canonical conversation structure and relevant generation options in cache identity. Disable multimodal caching until image identity is represented. Scope entries using authenticated identity, and decide explicitly which requests are safe for fuzzy matching.

## S8 — Inconsistent redaction of upstream errors

**Severity:** Medium  
**Evidence:** Source inspection; no real credentials were exposed during testing.

**Affected code:**

- [`llm/orchestration/provider_call.py:32`](../src/gateway/llm/orchestration/provider_call.py#L32).
- [`llm/orchestration/finalization.py:23`](../src/gateway/llm/orchestration/finalization.py#L23).
- [`llm/orchestration/pipeline.py:145`](../src/gateway/llm/orchestration/pipeline.py#L145).
- [`llm/api/routes.py:70`](../src/gateway/llm/api/routes.py#L70).
- [`llm/service.py:110`](../src/gateway/llm/service.py#L110).
- [`llm/providers/http.py`](../src/gateway/llm/providers/http.py) and individual adapters.

Several paths return or persist truncated `str(exc)` values and upstream response bodies without applying the existing `safe_error()` helper. Truncation limits length but does not remove secrets. Gemini requests include the API key in the query string, making any URL-bearing errors particularly sensitive.

**Potential impact:** Credential or request-content disclosure through HTTP errors, SSE frames, attempt histories, usage reads, audit storage, or logs. Exposure depends on the upstream error contents.

**Proposed remediation:** Return stable public error codes and sanitized messages. Apply consistent redaction before diagnostic persistence, and keep sensitive diagnostics behind appropriate access controls. Avoid credential-bearing URLs in logs and errors.

## S9 — Incomplete resource and complexity limits

**Severity:** Medium  
**Evidence:** Source inspection and small local model/schema probes; no load testing was performed.

**Affected code:**

- [`llm/models.py:221`](../src/gateway/llm/models.py#L221): no batch-size or concurrency ceiling.
- [`llm/orchestration/pipeline.py:100`](../src/gateway/llm/orchestration/pipeline.py#L100): streaming bypasses the ordinary provider-call semaphore.
- [`llm/service.py:92`](../src/gateway/llm/service.py#L92): embeddings lack a common concurrency gate.
- [`llm/orchestration/structured_output.py`](../src/gateway/llm/orchestration/structured_output.py): validation and repairs lack common workload limits.
- [`llm/economics/meter.py:32`](../src/gateway/llm/economics/meter.py#L32): usage records grow without a retention bound.
- [`llm/providers/gemini/schema.py`](../src/gateway/llm/providers/gemini/schema.py): reference expansion has no resulting-size bound.
- [`llm/providers/gemini/context_cache.py`](../src/gateway/llm/providers/gemini/context_cache.py): the local resource map has no overall capacity bound.

The batch model accepted `max_concurrency=1000000`. Existing schema node/depth checks accepted a tiny recursive reference whose validation produced `RecursionError`. Request text, data-URL images, message counts, and tool schema sizes also lack comprehensive application-level bounds. The remote-image byte cap applies per fetch rather than to the whole request, and DNS resolution is synchronous.

**Potential impact:** Excessive queued tasks, memory growth, CPU consumption, event-loop blocking, connection pressure, or provider spending. Effective limits may exist in deployment infrastructure, which was not assessed.

**Proposed remediation:** Establish request-body and field limits, maximum batch size, bounded queues, and common concurrency controls covering all provider work. Bound schema validation and expanded schemas. Add retention/capacity limits and total request deadlines. Preserve cancellation rather than treating it as an ordinary retryable failure.

## S10 — Shared address space passes URL validation

**Severity:** Medium; network-dependent  
**Evidence:** A local address-validation probe accepted `http://100.64.0.1/x`; no connection was attempted.

**Affected code:** [`security/ssrf.py:20`](../src/gateway/security/ssrf.py#L20).

The guard rejects several address classifications but does not explicitly exclude shared address space. `100.64.0.0/10` is non-globally-routable space defined for shared networking uses, distinct from RFC 1918 private addresses.

**Potential impact:** Access to services reachable through shared address ranges from the gateway host. Actual exposure depends on host and network routing.

**Proposed remediation:** Define an explicit public-destination policy that excludes shared and other disallowed special-use ranges, while retaining checks for embedded IPv4 addresses, every DNS result, and redirects. Add regression cases for these ranges.

**Reference:** [RFC 6598 — IANA-Reserved IPv4 Prefix for Shared Address Space](https://www.rfc-editor.org/rfc/rfc6598).

## Additional hardening observations

These are narrower observations or deployment-dependent concerns, rather than additional confirmed exploit chains:

- **Audit storage is not tamper-proof.** `AuditStore` exposes append/query operations, but SQLite itself is not protected against modification by a principal with filesystem access. The helper does not explicitly impose private file permissions.
- **The semantic cache contains content.** It stores prompt excerpts and full responses in plaintext SQLite. Access permissions, backup handling, and retention should reflect that sensitivity.
- **Agent-trace filtering is incomplete by construction.** The proxy removes a short list of content keys rather than selecting approved output fields. Sensitive content under other keys can survive, and the upstream response has no explicit size cap.
- **Startup cleanup is incomplete.** Some partial construction failures can leave previously created resources unclosed. Startup errors also include raw exception messages.
- **Tool-call output is untrusted.** The gateway returns parsed tool calls but does not execute them. A downstream executor must validate allowed tool names, arguments, authorization, and side effects before execution.
- **Capability flags are descriptive.** Provider capability reporting is not a security boundary and does not consistently constrain routing.
- **The persistent call ledger is not the current call-history write target.** Finalization writes the process-local meter and durable audit store, so operators should not assume the `calls` table is complete.

## Existing protective measures

- Canonical `/api/` paths reject missing or incorrect bearer credentials.
- Inspected database queries parameterize request-derived values; dynamic migration identifiers come from fixed code.
- YAML loading uses `safe_load()`.
- The image fetcher pins validated DNS results, rechecks redirects, and limits fetched bytes.
- Trace and refusal stores are bounded and use allow-listed metadata.
- The agent-trace proxy restricts its destination to the configured runtime.
- Audit write failures propagate rather than being silently discarded.

These controls are useful, but they do not eliminate the findings above.

## Verification record

| Check | Result |
| --- | --- |
| Existing SSRF regression tests | 3 passed; pytest cache and bytecode writes disabled. |
| Canonical versus legacy authentication | Canonical provider route returned 401; legacy route returned 200 without credentials. |
| Frontend containment | Encoded traversal returned a benign repository file with an in-memory test root. |
| External schema retrieval | Loopback retrieval attempt intercepted before network access. |
| Budget identity omission | Request without identity admitted despite a zero-dollar policy for a named tenant. |
| Compatible streaming usage | Usage-bearing mock stream retained model confirmation but no final usage/result. |
| Batch accounting | Caller flag reduced synthetic projected pricing without changing submission mode. |
| Cache conversation identity | Different message structures generated identical cache inputs. |
| Schema recursion | Small self-reference produced `RecursionError`. |
| Special-use address handling | Shared-space IP accepted by validation; no connection attempted. |

No paid provider calls or live attacks were performed. This report is not a guarantee that all vulnerabilities have been identified. No application fixes have been applied; they require the owner's approval.

## Suggested remediation order

1. Close legacy authentication gaps, contain frontend file access, and disable external schema retrieval: **S1–S3**.
2. Establish verified caller identity and correct spending enforcement: **S4–S6**.
3. Correct cache identity and sanitize error paths: **S7–S8**.
4. Add workload limits and complete special-use address exclusions: **S9–S10**.
