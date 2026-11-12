# Metric Calculation Methodology

Implementation Detail for Review and Refinement

This document describes how each metric in the system is calculated in practice.

The intent is to make each implementation choice explicit so that assumptions can be reviewed, challenged, or improved.

All calculations are performed under strict point-in-time rules.

Fundamental data is assumed to become available 45 trading days after the reporting date. This lag is applied mechanically before any merge with price data. At any date, only information that would have been observable at that date is used.

After the lag, quarterly fundamental values are carried forward until replaced by newer reported data. No forward filling is applied prior to the lag.

Missing or economically undefined inputs (for example, non-positive market capitalisation or zero book equity) are not computed. In such cases, the resulting metric is set to NaN and excluded from downstream calculations on that date.

Outliers are controlled using cross-sectional winsorisation at the 1st and 99th percentiles, applied independently for each factor on each date, before any standardisation. 

Six factors are computed daily: value, quality, size, momentum, low volatility, and short-term reversal.

Each factor follows the same processing sequence:

Value is calculated as book equity divided by market capitalisation. Book equity is defined as equity share capital plus reserves. No adjustments are made for deferred taxes, intangibles, minority interests, or other balance-sheet items.

Quality is calculated as return on equity using net profit divided by book equity. Net profit corresponds to the most recent reported fiscal period available after the 45-day lag. Loss-making firms are included without truncation.

Size is calculated as the natural logarithm of market capitalisation. The log transform is applied to compress the upper tail of the size distribution. Stocks with non-positive market capitalisation are excluded.

Momentum is calculated as the price return from 12 months ago to 1 month ago, using prices at t−252 and t−21 trading days. The most recent month is intentionally excluded.

This raw momentum series is not used directly. Instead, it is normalised relative to the stock’s own recent history by subtracting a rolling 252-day mean and dividing by a rolling 252-day standard deviation. This ensures that momentum scores reflect how strong recent performance is relative to that stock’s typical momentum, rather than in absolute terms.

Low volatility is calculated from realised volatility over the prior 126 trading days using daily returns. As with momentum, the realised volatility series is normalised relative to its own rolling 252-day mean and standard deviation. This makes the signal relative to the stock’s own volatility history.

Minimum observation thresholds are enforced for all rolling calculations. If insufficient data is available, the metric is set to NaN for that date.

Reversal is calculated as the negative of the 21-day lagged return.

After winsorisation, each factor is standardised across stocks on the same date.

Standardisation is sector-aware where possible. Stocks are grouped by sector, and for each sector on each date, the number of stocks with valid factor values is counted.

If a sector has at least 5 valid stocks, standardisation is performed within that sector. The sector mean is subtracted from each stock’s value, and the result is scaled using the sector’s standard deviation.

If a sector has fewer than 5 valid stocks, sector information is ignored for that sector on that date. In this case, standardisation is performed using the global cross-section of all stocks with valid values on that date.

This decision is made independently for each sector and each date. A flag is stored internally indicating whether a factor score was produced using sector-level or global statistics.

All cross-sectional standard deviations use sample statistics (ddof = 1).

After standardisation, factor signs are adjusted so that higher scores consistently correspond to stronger expected performance.

Size and volatility scores are inverted so that smaller-capitalisation and lower-volatility stocks receive higher scores. This inversion is purely a convention and does not alter cross-sectional rankings.

Predictive strength is evaluated using stock-level regressions of future returns on factor scores, estimated separately for each stock and factor.

Factor scores are sampled at month-end, using the last available observation for each stock in each calendar month. Each score is aligned with the stock’s forward 21-trading-day return.

A minimum of 24 observations is required to estimate a regression. The factor score is mean-adjusted prior to estimation to improve numerical stability.

Regressions are estimated using ordinary least squares. No adjustments are made for heteroskedasticity or serial correlation. As a result, t-statistics should be interpreted as relative indicators of signal strength, not as formal hypothesis tests.

Daily factor returns are constructed using simple long–short portfolios.

On each trading day and for each factor:

A minimum of 6 stocks is required on a day to compute a factor return.

These daily factor returns are then used in a linear factor model at the stock level. Each stock’s daily returns are regressed on the contemporaneous factor returns to estimate factor betas.

Stocks are not excluded from the factor portfolios when estimating their own exposure. This simplifies implementation but mechanically increases explanatory power.

From the factor regression, R-squared is computed as the fraction of total return variance explained by the factor model.

Residual volatility is computed as the standard deviation of the regression residuals using population statistics (ddof = 0) and is interpreted as stock-specific risk.

Total variance is decomposed additively into factor-driven and residual components. No covariance term exists by construction under OLS.

A separate set of descriptive metrics is computed directly from daily return series.

These include annualised returns and volatility, cumulative performance, drawdowns and drawdown duration, directional statistics (positive vs negative days), and tail risk measures based on historical percentiles.

All metrics are computed mechanically from realised returns. No parametric distributional assumptions are imposed.

Time-varying volatility is modelled using a standard GARCH(1,1) specification estimated via maximum likelihood.

From the fitted model, derived quantities such as volatility persistence, long-run volatility, and the half-life of volatility shocks are computed. These outputs are descriptive and are not used directly in downstream calculations.

Daily VIX values are classified into low, medium, and high volatility environments based on their position relative to historical percentiles.

Stock returns are analysed separately within each environment to assess how behaviour changes with market volatility.

Separately, sensitivity to changes in VIX is estimated using a simple regression of stock returns on daily percentage changes in VIX, subject to a minimum observation requirement.

Daily returns are classified as positive or negative based on sign.

From this classification, the system computes how often returns continue in the same direction versus switching direction from one day to the next. Longer-horizon patterns are inferred by chaining these observed day-to-day frequencies.

No forecasting model is imposed; the analysis is purely descriptive.

