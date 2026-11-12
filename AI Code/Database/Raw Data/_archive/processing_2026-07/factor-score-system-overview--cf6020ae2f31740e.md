# 1. Problem Statement



The mandate for this project was straightforward:

build a daily factor-scoring module that assigns six widely-used style-factor scores to each stock in the internal universe. These scores are intended to sit alongside the fundamental analysis already used by the equity research team, providing a systematic, relative view of a stock’s characteristics on any given day.

The delivered module satisfies this direct requirement. In addition, and only to ensure internal consistency and robustness, the system also computes several diagnostic components such as long–short factor returns, regression-based risk decomposition, and factor-dynamics metrics. These diagnostics do not expand the user-facing output; instead, they help validate that the factor scores behave in a stable and interpretable manner.

All factor scores are computed daily from point-in-time aligned data. The process combines strict data hygiene, statistical standardisation, and consistent sign conventions.

All fundamentals are shifted forward by 45 days to reflect publication lags, and merged with daily prices using a backward merge.

I believe this ensures that the factor scores are constructed without accidentally using future information.

Before z-scoring any input, the following steps are applied:

These steps contribute to stable and interpretable factor signals, especially for large-cap names and volatile sectors.

Every factor score is a daily cross-sectional z-score, meaning:

Because all signs are aligned to the conventional direction,

a positive score consistently represents “more exposure” to the intended factor.

To make the scoring methodology concrete, below are the latest scores for two representative banks in the coverage universe.

Interpretation: ICICI appears cheaper and low-vol, but very large and with below-average momentum.

Interpretation: SBI exhibits strong value characteristics and moderate low-vol exposure, with otherwise neutral behaviour on momentum and reversal.

To validate the factors, the system constructs tertile long–short portfolios each day:

top 1/3 minus bottom 1/3 of stocks.

These returns are used only as diagnostic regressors and not for portfolio construction.

I believe this helps confirm whether the factor definitions are directionally sensible.

For each stock:

This is not intended to provide investment signals, but instead to check whether the constructed factors co-move with individual stocks in a stable manner.

Only the most recent ~400 trading days are used.

Metrics include:

I believe this helps ensure that factor exposures behave in a stable and interpretable way across time.

The system rests on several modelling choices:

I believe these assumptions are reasonable for a first iteration and can be refined later.

These foundational papers shape the interpretation and construction of the factor definitions used.

