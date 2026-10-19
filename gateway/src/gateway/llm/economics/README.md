# Pricing, budgets, and usage accounting

This folder converts token usage into configured USD costs, reserves spending capacity before chat calls, and records which caller is spending.

| File | Responsibility |
| --- | --- |
| `pricing.py` | Loads version-1 `pricing.yaml`; resolves exact model prices, provider-prefixed model aliases, patterns, provider defaults, then an unpriced fallback. Projects costs and computes actual costs with prompt-cache multipliers. |
| `budget.py` | Defines `Principal` (agent and session); loads version-1 `budgets.yaml`, merges runtime SQLite overrides, matches principal policies, atomically reserves projected costs, and reconciles or releases reservations. |
| `__init__.py` | Exports the main accounting objects. |

## Chat accounting flow

The orchestration budget stage projects the largest cost among candidate providers using estimated input size and the requested output limit. `BudgetController.admit()` checks matching agent/session policies inside a SQLite `BEGIN IMMEDIATE` transaction. A breached policy results in HTTP 402 before the chat provider is called.

Finalization uses the available provider result to calculate actual cost, reconciles the reservation, and appends one row to the [call ledger](../../ledger/README.md). Without a provider result, it releases the reservation and records zero cost. Runtime limits, budget entries and ledger rows all persist in the gateway database. Clearing a runtime override can reveal a policy still present in the YAML file.

Periods use fixed epoch-aligned windows; `month` is a 30-day interval rather than a calendar month. Policy objects retain `include_errors`, but current finalization decides reconciliation from result availability rather than consulting that flag. Pricing is operator-configured data, not a live vendor-price feed. See [orchestration](../orchestration/README.md).
