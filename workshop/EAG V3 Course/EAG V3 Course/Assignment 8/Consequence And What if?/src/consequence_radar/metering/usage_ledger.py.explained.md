# `metering/__init__.py` explained

A thread-safe budget enforcer for external calls (LLM generations and grounded searches) made during one pipeline run. It doesn't do accounting/billing — it exists purely to make a run fail fast (`BudgetExceeded`) once it has consumed too many calls, too much wall-clock time, or too many search calls.

## `BudgetExceeded(RuntimeError)`

Plain marker exception, raised by every guard below with a message identifying which budget tripped (`"wall-clock budget exceeded"`, `"model-call budget exceeded"`, `"search-call budget exceeded"`).

## `UsageSnapshot` (frozen dataclass)

An immutable point-in-time read of the ledger: `calls`, `input_tokens`, `output_tokens`, `elapsed_seconds`, `max_calls`, `max_wall_time_seconds`, `searches` (default 0), `max_searches` (default 0). All fields are built positionally by `UsageLedger.snapshot()` — reordering the dataclass fields without updating that call site would silently mis-assign values rather than error, since there's no keyword construction anywhere.

Despite tracking `input_tokens`/`output_tokens`, nothing in this file enforces a token budget — they're recorded for reporting only. The only enforced budgets are call counts and wall-clock time.

## `UsageLedger`

### `__init__(max_calls, max_wall_time_seconds, max_searches=None)`

If `max_searches` isn't given, it defaults to `max_calls` — i.e. the search budget defaults to being equal to the generation-call budget, not unlimited. The inline comment explains why searches are metered *separately* from model-call generations at all: grounded search hits the same underlying API but a single run issues far more searches than generations, so if searches counted against the generation budget they'd starve the pipeline of the calls it actually needs to finish.

Internal counters (`_calls`, `_searches`, `_input`, `_output`) start at 0, `started` is set once via `time.monotonic()` at construction and never mutated again. A `threading.Lock` guards the counters.

### `guard_external_call(kind="model")`

Call this immediately before making an external API call (of either kind). Under the lock:
1. Checks wall-clock elapsed time first, unconditionally, regardless of `kind` — if the run has been going longer than `max_wall_time_seconds`, it raises immediately even if call/search budgets still have headroom. This ordering is deliberate and is what `test_wall_clock_guard_precedes_both_budgets` pins.
2. If `kind == "search"`, checks/increments the search counter against `max_searches` and returns.
3. Otherwise checks/increments the model-call counter against `max_calls`.

Note the counter increments *before* the call succeeds or fails — this guards against a caller intending to spend budget, not against confirmed successful calls. A caller that calls `guard_external_call()` and then has the actual API call fail/retry still has that budget slot consumed; retries are not free.

### `guard_time()`

A lighter-weight, lock-free check of just the wall-clock budget, for use at checkpoints where a caller wants to bail early without attempting a call. Safe without the lock because `started` is set once at construction and never mutated afterward — there's no race to protect against on a read-only, immutable field.

### `record(input_tokens=0, output_tokens=0)`

Accumulates token counts under the lock. Called after a real API response is known, to track usage after the fact — separate from the pre-call `guard_external_call`. Purely informational; nothing reads these totals to enforce a limit.

### `snapshot()`

Returns a `UsageSnapshot` built under the lock from current state plus `round(elapsed, 3)`.

## Connections

`UsageLedger`/`BudgetExceeded` are imported by `pipeline/__init__.py` (the run orchestrator, which presumably constructs one ledger per run using `max_model_calls_per_run`/`max_wall_time_seconds`/`max_search_queries_per_run` from `Settings`), and by `providers/search/__init__.py` and `providers/model/__init__.py` — the two places that actually make external Gemini API calls and would call `guard_external_call("search")` / `guard_external_call()` respectively before issuing a request, and presumably `record()` after receiving a response.
