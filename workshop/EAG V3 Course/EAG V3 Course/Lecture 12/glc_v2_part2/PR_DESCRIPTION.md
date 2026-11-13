# PR: /v1/chat has no wall-clock timeout on the provider call (Invariant 8)

**Branch:** `part2-run-timeout` (already committed, commit `ae7f82e`)

## Bug

`chat()` in `glc/routes/chat.py` never bounds how long it waits on
`provider.chat()` (non-streaming) or `provider.stream()` (streaming). A
provider that stalls — dead connection, buggy SDK, slow/compromised
upstream — blocks the request indefinitely. The existing retry-on-failure
logic only fires when the provider *raises*; an await that never resolves
never reaches it.

Breaks **Invariant 8** ("every run has hard limits on time, tokens, tool
calls, and cost"). Reachable by **attacker role 1** — an outsider on the
public internet with no credentials, since `/v1/chat` has no auth in this
reference build — simply by getting any routed provider to stall. Not one
of the Sections 6/7 findings (`timeout`/`hang` do not appear in that list).

## Reproduce (fresh checkout, no live provider or deployment needed)

```
git clone <glc_v2> && cd glc_v2
uv sync
uv run pytest -q tests/test_provider_call_timeout.py
```

Both tests fail against the unmodified tree: a fake provider whose
`chat()`/`stream()` sleeps 0.3s takes the full 0.3s every time — there is
no ceiling to configure at all.

## Fix

Wrap every `provider.chat()` call in `asyncio.wait_for(...,
timeout=GLC_PROVIDER_TIMEOUT_SECONDS)` (default 60s), and wrap the
streaming loop's `provider.stream()` consumption in `asyncio.timeout(...)`.
A wall-clock timeout on the first non-streaming attempt is treated as
non-retryable (retrying the same stuck provider only doubles the cost for
no benefit) and falls through to the existing "log and try the next
candidate provider" path, unchanged.

Full reference suite: 249 passed before, 251 passed after (2 new tests,
no regressions). `ruff check` clean.

## Known limitation, stated up front

The streaming timeout (`asyncio.timeout(...)` wrapping the whole `async
for` loop) bounds **total stream duration**, not per-chunk idle time. A
legitimate stream that runs past the configured ceiling (default 60s) gets
cut off even if it was still actively producing chunks. This is a
deliberate, simple interpretation of Invariant 8's "hard limit on time" —
operators with genuinely long-running completions should raise
`GLC_PROVIDER_TIMEOUT_SECONDS` accordingly. An idle/inter-chunk timeout
(reset on every chunk rather than bounding the whole call) would be more
precise but is a larger change; flagged here rather than silently shipped
as if it were the same thing.

## To file

1. Fork `theschoolofai/glc_v2` under your own account.
2. `git remote add fork <your-fork-url>` in this worktree
   (`glc_v2_part2/`, already on branch `part2-run-timeout` with the fix
   committed).
3. `git push fork part2-run-timeout`
4. Open the PR against `theschoolofai/glc_v2:main`, title/body from this
   file. Check open PRs first — first filer wins on duplicates, and this
   is a fairly discoverable bug.
