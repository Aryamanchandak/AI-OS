# Comprehensive Performance Improvement Plan - Core Inflation Predictor V5.0

Based on your current results and the V5.0 upgrade document, here's a strategic plan to improve laggards without dropping models, focusing on empirically-driven enhancements.

You're right - the goal is to elevate underperforming models, not eliminate them. The ensemble's strength comes from diversity, even if individual components underperform.

Rationale: This is a bug fix, not an enhancement. Essential.

Rationale: Your document suggests 14 values, but 6 strategic windows (1-4 years) balance exploration vs. runtime. For monthly CPI data, testing 6-60 months isn't meaningful.

Rationale: Currently disconnected infrastructure serves no purpose. This is a must-fix.

Implementation:

Rationale: Your results show RollingHybrid dominates, but empirical validation prevents bias. Limit comparisons to 2 scalers per model type to control runtime.

Rationale: SARIMA's R² of -131 to -259 suggests model misspecification, not just poor tuning. The current approach likely uses exogenous variables incorrectly (SARIMA doesn't support them - only SARIMAX does).

Rationale: RMSE of 0.12-0.34 with negative R² suggests severe overfitting or training instability. Your CPI datasets (~120-150 points) are small for deep learning.

Rationale: XGBoost's R² of -2 to -8 indicates severe overfitting. Small CPI datasets need heavy regularization.

Rationale: RF performs well with RollingHybrid but poorly otherwise. Focus on preventing overfitting rather than model capacity.

Rationale: KAN's inconsistency (RMSE 0.10-0.58) suggests scaling issues. Your V5.0 doc notes KANs prefer monotonic/bounded scaling.

Rationale: Your base models (ARIMAX, VAR, BVAR) are highly correlated. ElasticNet handles this better than Ridge/Lasso per your V5.0 document.

Rationale: Prevents poor models from degrading ensemble. Simple and effective.

Rationale: Tree models and neural nets benefit from explicit lags. Statistical models don't need them.

Rationale: Captures temporal patterns that trees/DL might miss. Avoid for statistical models to prevent multicollinearity.

Rationale: Use cautiously - can introduce data leakage if not careful. Only for tree/DL models.

Reason: Testing 14 windows is computationally expensive with diminishing returns. CPI data doesn't benefit from 5-year windows (60 months). Use [12, 18, 24, 30, 36, 48] instead.

Reason: Your V5.0 document correctly justifies 3-fold for monthly data (~120-150 points). 5-fold would create folds of ~24-30 observations - too small for meaningful validation. Keep 3-fold.

Reason: Implement AFTER confirming models work. Parallelization adds complexity and debugging difficulty. Defer to V5.1 or V6.0.

Reason: ElasticNet is theoretically and empirically superior for correlated models. Testing all four wastes time. Use ElasticNet only.

Reason: CPI data rarely has true outliers (central banks smooth them). RobustScaler already handles this. Skip unless specific outliers identified.

Reason: You only have ~10-15 features per dataset. Feature selection adds complexity without benefit. Skip.

