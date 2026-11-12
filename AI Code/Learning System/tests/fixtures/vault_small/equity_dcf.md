---
tags: [equity, valuation, DCF, CFA-L1]
domain: Equity Investments
---

# Discounted Cash Flow Valuation

Discounted Cash Flow (DCF) valuation estimates the intrinsic value of a company or asset by discounting its expected future cash flows back to the present.

## Gordon Growth Model (Dividend Discount Model — Constant Growth)

The Gordon Growth Model (GGM) values a stock that pays dividends growing at a constant rate indefinitely:

```
V₀ = D₁ / (r - g)
```

Where:
- V₀ = intrinsic value today
- D₁ = expected dividend next period
- r = required rate of return
- g = constant dividend growth rate

**Critical constraint**: r must be greater than g, or the model produces a negative or undefined value.

If D₀ (current dividend) is given instead of D₁, compute D₁ = D₀ × (1 + g).

## Free Cash Flow to Equity (FCFE)

FCFE is the cash flow available to common shareholders after all expenses, reinvestment, and debt obligations have been met:

```
FCFE = Net Income - (1 - DR) × (FCInv - Dep) - (1 - DR) × ΔWC
```

Where DR is the debt ratio (proportion of investment funded by new debt).

FCFE is discounted at the cost of equity (r_e).

## Free Cash Flow to Firm (FCFF)

FCFF is the cash flow available to all capital providers (equity and debt holders):

```
FCFF = EBIT × (1 - Tax Rate) + Depreciation - FCInv - ΔWC
```

FCFF is discounted at the Weighted Average Cost of Capital (WACC).

## Relationship Between FCFE and FCFF

```
FCFE = FCFF - Interest × (1 - Tax Rate) + Net Borrowing
```

Use FCFF when capital structure is changing or unstable; use FCFE when the firm has a stable leverage ratio.
