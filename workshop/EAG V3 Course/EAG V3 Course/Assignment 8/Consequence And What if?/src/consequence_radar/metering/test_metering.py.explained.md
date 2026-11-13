# `metering/test_metering.py` explained

Four focused tests against `UsageLedger`/`BudgetExceeded`, all synchronous and single-threaded.

## `test_model_call_guard_is_hard_and_thread_safe`

The name promises a thread-safety test, but the body never spawns a thread — it's a straightforward sequential check: a ledger with `max_calls=2` allows exactly two `guard_external_call()`s, raises `BudgetExceeded` on the third, and `record(10, 5)` followed by `snapshot().input_tokens == 10` confirms token recording works. The "hard" half of the name is accurate (the budget is a hard stop, not a soft warning); the "thread-safe" half is asserted only by the presence of the lock in the implementation, not exercised by this test. Anyone relying on this test to catch a concurrency regression in `UsageLedger` would be trusting an untested claim.

## `test_searches_do_not_consume_the_generation_budget`

Builds a ledger with `max_calls=2, max_searches=5` and confirms the two counters are fully independent: five search calls succeed and don't touch the model-call budget (both `guard_external_call()` calls afterward still succeed), a sixth search call raises with the search-specific message, and a third model call raises with the model-specific message. This is the regression test for the core design decision in `UsageLedger.__init__` — that grounded search must not share a budget with generation calls, since one run issues far more searches than generations and sharing a pool would starve the pipeline of the calls it needs to actually finish.

## `test_search_budget_defaults_to_the_model_budget`

With no `max_searches` argument (`UsageLedger(1, 60)`), confirms the search budget silently equals `max_calls` (1) rather than being unlimited — one search succeeds, a second raises `"search-call budget exceeded"`. Guards against someone "simplifying" the default to `None`/unbounded, which would remove protection against runaway search usage on any ledger constructed without an explicit `max_searches`.

## `test_wall_clock_guard_precedes_both_budgets`

Constructs a ledger with `max_wall_time_seconds=0` (so it's expired the instant it's checked) but generous `max_calls=10`, and confirms both `"model"` and `"search"` kinds raise the wall-clock message, not a call/search-budget message. This pins the specific order of checks inside `guard_external_call` — wall-clock is evaluated first and unconditionally — so a run that has both exhausted its time and its call budget always reports the time-based reason, which matters for whoever reads the error message to diagnose why a run stopped.

## Connections

Imports `BudgetExceeded`, `UsageLedger` directly from `consequence_radar.metering`. No other module dependencies.
