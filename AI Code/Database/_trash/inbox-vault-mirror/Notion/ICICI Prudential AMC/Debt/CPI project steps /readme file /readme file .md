

# Multi-Target Time-Series Forecasting Framework

Production-ready forecasting framework for 3 target variables jointly using 998 input features on daily-frequency time-series data. Features rolling-window evaluation, Optuna hyperparameter tuning for all models, and modular architecture optimized for high-dimensional data.

All models now have Optuna tuning settings in config.py, optimized for 998-dimensional input:

Each model config has:

Easy disable for testing:

Each model has dedicated config section:

All models must implement:

The orchestrator uses utils.generate_rolling_windows:

For each model you've implemented:

