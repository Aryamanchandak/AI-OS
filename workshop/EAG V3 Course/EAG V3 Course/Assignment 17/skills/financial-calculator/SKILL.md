---
name: financial-calculator
description: This skill should be used whenever the run builds or changes index.html for a financial calculator, such as a fee, rebalancing, interest or allocation tool. It carries the working order and the mistakes that make such a tool give wrong numbers.
when_to_use: an index.html calculator is being written or edited and must pass checks/check_tool.js
keywords: [calculator, financial, fee, rebalance, portfolio, index.html, calculate, check]
---
The check is the judge: `node checks/check_tool.js index.html`. It runs the
`calculate(input)` function from the page's `<script id="calc">` block against
examples the user confirmed. You cannot edit it. Run it after every change.

Work in this order.

1. Write the arithmetic first, as `function calculate(input)`, before any styling.
2. Run the check. Read each failing line: it names the example, the output key,
   the expected value and what you returned.
3. Fix the rule that line points at. Change one thing, then run the check again.

Mistakes that account for most wrong numbers.

**Tiered rates applied to the whole amount.** "1% on the first 1,000,000 and
0.75% on the next 4,000,000" means each rate applies only to the slice inside
its tier. Multiplying the whole amount by the rate of the tier it lands in is wrong.

**Percent versus fraction.** A weight entered as 50 means 50%, so divide by 100
once. Return weights in the same unit the specification's examples use.

**Rounding too early.** Round only the final figures, and the way the
specification says. Rounding intermediate values shifts totals by a cent.

**Floating point at the half.** `Math.round(x * 100) / 100` misrounds some
halves. Use `Math.round((x + Number.EPSILON) * 100) / 100`.

**Minimums and caps forgotten.** A minimum or maximum charge is a rule like any
other. Apply it after the main calculation and report whether it applied when
the specification has an output for that.

**Text inputs.** Form values are strings. Convert with `Number(...)` and treat
blank or invalid input as 0 rather than returning NaN.

If the check still fails after you fixed what it named, re-read the rule in the
specification rather than adjusting numbers until they match. Never hard-code an
example's expected answer, and never remove a rule to get to green.
