# `providers/search/test_search.py` explained

**Last updated:** 2026-08-24  
**Source lines:** 139  
**Language:** Python / pytest

## What this file does

In plain English, this file checks the seam between Gemini grounded search and the rest of Consequence Radar without making a network call. It builds small look-alike Gemini responses, gives them to a search provider created without running its real credential-dependent constructor, and checks the sources, snippets, tool configuration, and usage accounting that come back.

At developer level, `StubLedger`, `StubModels`, `web_chunk()`, `support()`, `response()`, and `make_provider()` (L6–59) are test doubles for `UsageLedger` and `google.genai`. The six tests at L62–139 exercise `GeminiGoogleSearchProvider.search()` rather than its constructor, so they verify response parsing but not authentication or SDK-client construction.

## Execution and data flow

Each test creates a response shaped like the subset of a Gemini response used by production code: `candidates[*].grounding_metadata.grounding_chunks`, `grounding_supports`, and `usage_metadata` (L18–35). `make_provider()` then uses `object.__new__` (L53) to bypass `GeminiGoogleSearchProvider.__init__`, directly injecting settings, the ledger, callback, and fake client (L54–58). Calling `provider.search(...)` therefore runs all production parsing and metering logic while the final `generate_content` call is captured by `StubModels.generate_content()` (L43–45).

The primary happy-path test (L62–81) checks that both `google_search` and `url_context` are passed to the SDK, that support segments referring to the same grounding chunk are concatenated in encounter order, and that two chunks become two `SearchResult` objects. The remaining tests prove that URL Context can be disabled (L84–92), unmatched chunks get an empty snippet (L95–102), URL Context tool-use tokens are included in input cost and the audit callback (L105–116), a missing tool-token field behaves as zero (L119–128), and duplicate URLs are removed before the caller's result cap is applied (L131–139).

## State, branches, and side effects

The file owns only per-test in-memory state. `StubLedger.guarded` records call-budget checks but no assertion currently verifies it (L7–15), while `StubModels.calls` preserves the SDK arguments for later inspection (L38–49). There is no disk, database, credential, or network side effect.

The important branch is `enable_url_context_search`: `True` should produce both tools, while `False` should leave Google Search alone. The response parser also branches when support text is absent, when tool-use token metadata is absent, and when a URL has already been emitted. These tests cover each branch individually.

## Honest gaps and risks

- The constructor and missing-key error are not tested because `object.__new__` bypasses `__init__` (L53).
- `StubLedger.guard_external_call()` records its argument (L11–12), but no test asserts that production calls it with `"search"`.
- The fixtures assume Gemini's Python SDK object attributes. They do not test malformed `candidates`, missing `grounding_metadata`, an SDK exception, or a candidate whose `grounding_chunks` is `None`.
- Snippet concatenation is checked, but repeated support text is not deduplicated and whitespace is not normalised; the production code preserves both behaviours.
- The suite confirms token accounting, not pricing. `tool_use_prompt_token_count` is folded into input tokens because that is how this application chooses to represent cost.

## Developer notes

Keep this test beside `providers/search/__init__.py`; the project deliberately colocates stage code and focused unit tests. If Gemini renames grounding metadata fields, update the fake response shape and production parser together. A passing test only proves compatibility with this modeled response shape, not the live service.
