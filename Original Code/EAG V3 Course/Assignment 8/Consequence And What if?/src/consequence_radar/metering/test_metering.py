import pytest
from consequence_radar.metering import BudgetExceeded, UsageLedger


def test_model_call_guard_is_hard_and_thread_safe():
    ledger=UsageLedger(2,60);ledger.guard_external_call();ledger.guard_external_call()
    with pytest.raises(BudgetExceeded): ledger.guard_external_call()
    ledger.record(10,5);assert ledger.snapshot().input_tokens==10


def test_searches_do_not_consume_the_generation_budget():
    ledger = UsageLedger(2, 60, max_searches=5)
    for _ in range(5):
        ledger.guard_external_call("search")
    # The generation budget is untouched by all that searching.
    ledger.guard_external_call()
    ledger.guard_external_call()

    with pytest.raises(BudgetExceeded, match="search-call budget exceeded"):
        ledger.guard_external_call("search")
    with pytest.raises(BudgetExceeded, match="model-call budget exceeded"):
        ledger.guard_external_call()

    snapshot = ledger.snapshot()
    assert (snapshot.calls, snapshot.searches) == (2, 5)
    assert (snapshot.max_calls, snapshot.max_searches) == (2, 5)


def test_search_budget_defaults_to_the_model_budget():
    ledger = UsageLedger(1, 60)
    ledger.guard_external_call("search")
    with pytest.raises(BudgetExceeded, match="search-call budget exceeded"):
        ledger.guard_external_call("search")


def test_wall_clock_guard_precedes_both_budgets():
    ledger = UsageLedger(10, 0)
    for kind in ("model", "search"):
        with pytest.raises(BudgetExceeded, match="wall-clock budget exceeded"):
            ledger.guard_external_call(kind)
