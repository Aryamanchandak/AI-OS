---
tags: [fixed-income, duration, CFA-L1]
domain: Fixed Income
---

# Duration

Duration measures the sensitivity of a bond's price to changes in interest rates.

## Macaulay Duration

Macaulay Duration is the weighted average time (in years) to receive a bond's cash flows, where the weights are the present values of each cash flow as a proportion of the bond's price.

For a zero-coupon bond, Macaulay Duration equals the bond's time to maturity, because there is only one cash flow: the face value received at maturity.

For coupon-paying bonds, Macaulay Duration is always less than the time to maturity, because the investor receives periodic coupon payments before maturity.

## Modified Duration

Modified Duration measures the percentage change in a bond's price for a 1% (100 basis point) change in yield:

```
Modified Duration = Macaulay Duration / (1 + y/m)
```

Where y is the yield to maturity and m is the number of coupon payments per year.

A bond with Modified Duration of 5 will decrease in price by approximately 5% if yields rise by 1%.

## Dollar Duration (DV01)

Dollar Duration (also called DV01 or PVBP) measures the dollar change in a bond's price for a 1 basis point (0.01%) change in yield.

DV01 = Modified Duration × Bond Price × 0.0001

## Key Relationships

- Higher coupon → lower duration (more early cash flows)
- Longer maturity → higher duration
- Higher yield → lower duration
- Zero-coupon bond duration = maturity
