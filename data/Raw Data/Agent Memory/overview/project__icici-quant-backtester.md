---
name: ICICI Prudential Quant Backtester
description: Key facts about the NSE equity quantitative backtesting system at ICICI Prudential — architecture, data flow, current state, and known gaps
type: project
---

## What it is

A quantitative portfolio research tool for ICICI Prudential's equities team. Given a list of NSE-listed Indian equities and portfolio weights, it runs historical performance simulation (backtest) and risk measurement. It also supports a command-line path that takes a list of ISINs from a portfolio management export, translates them to tickers via a bridge module, optimizes weights using one of seven mathematical objectives, then backtests the result.

## Codebase location

`/Users/aryamanchandak/Documents/ICICI Prudential/Code/Quant/Quant-Backtester copy 2`

## Package structure (post-refactor, as of May 2026)

The codebase was reorganized from a flat single-directory layout into named sub-packages:
- `core/` — central configuration (ALL_TICKERS list ~170 stocks, factor constants, file paths)
- `ingestion/` — data loading from Bloomberg-format CSV files + pre-computed factor score cache
- `factors/` — full factor pipeline: 6 primary factors + 4 timeframe variants, PIT merge, winsorization, cross-sectional z-scoring
- `engine/` — backtester (buy-and-hold, per-day weight renormalization for NaN handling) + main orchestrator
- `optimizer/` — 7 objectives (equal_weight, inverse_vol, min_variance, max_sharpe via Charnes-Cooper, max_return, max_factor, min_factor), Ledoit-Wolf covariance, constraint feasibility check
- `risk/` — full risk engine (vol, beta vs NIFTY500, parametric VaR 95/99, historical ES, HHI, avg correlation, diversification ratio, drawdown); standalone covariance heatmap script (not in pipeline)
- `options/` — 4-stage filter (value → momentum direction → DMA alignment → RSI), synthetic options chain generator (Black-Scholes approximation with random OI)
- `bridge/` — ISIN-to-ticker translation via EQUITY_NSE.csv master reference
- `ui/` — Streamlit app (portfolio backtester + compare), standalone Portfolio_compare CLI, standalone Portfolio_compare_app Streamlit

## Critical architectural seams to know

1. **Optimizer is disconnected from the UI.** The Streamlit app only accepts manually typed weights. The optimizer is only reachable via the command-line path (run_from_filter in orch_backtest.py).

2. **Two factor score file formats.** New preferred format: `data/factor_data_paths/real.pkl`. Legacy fallback: `data/factor_data.pkl`. The options module always reads the legacy file — a known inconsistency.

3. **EQUITY_NSE.csv may be a stub.** The bridge code has a TODO comment to replace it with a real NSE equity listing download.

4. **Options overlay is entirely synthetic.** No real NSE options data is wired in. The generator and selector print prominent warnings about this.

5. **Three Portfolio Compare implementations** with overlapping logic: command-line module (hardcoded placeholder data path), embedded in main Streamlit app, standalone Streamlit app.

6. **Sector z-scoring is commented out.** Factor pipeline uses only global cross-sectional z-scoring. Sector-relative z-scoring constants exist in config but are not active.

7. **Risk engine lookback is hardcoded** at 252 days locally rather than reading from the central config.

## Data requirements

- `data/px.csv` — Bloomberg-format daily closing prices
- `data/fundamental.csv` — Bloomberg-format quarterly fundamentals
- `data/NSE500_RSINSE500.csv` — NIFTY500 benchmark (dayfirst=True date format)
- `data/EQUITY_NSE.csv` — NSE equity master (columns: SYMBOL, ISIN NUMBER)
- `data/factor_data_paths/real.pkl` — pre-computed factor scores (must run factor pipeline first)

## What is complete

Factor pipeline, backtester, risk engine, optimizer (all 7 objectives), bridge, Streamlit UI (manual weights only), test suite (backtester NaN handling, orchestrator helpers, optimizer constraints/objectives, bridge loader).

## What is incomplete

Optimizer not wired to UI; EQUITY_NSE.csv may be placeholder; options overlay synthetic only; three Portfolio Compare implementations not unified; Phase 4 (built-in stock filter) not started; no rebalancing or transaction costs.

**Why:** Context for future conversations about this project so the agent understands the current architecture without re-reading every file.

**How to apply:** When asked about this project, start from this structural understanding. Verify against current code state before advising on specific modules, as the codebase is actively evolving.
