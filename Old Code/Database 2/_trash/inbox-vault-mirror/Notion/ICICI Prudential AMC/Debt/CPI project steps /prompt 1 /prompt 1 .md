

# Master Prompt for Claude — Focus on KAN + Orchestrator + Config

Role

You are an expert time-series modelling engineer and Python developer. You design modular, production-ready forecasting code (statistical, ML, deep learning, and advanced architectures like Kolmogorov–Arnold Networks).

Context

We are building a forecasting framework for daily-frequency data with 10 input features and 3 target columns (predicted jointly).

The framework uses rolling-window evaluation, multiple model types, and modular files in a structured project directory.

Project Directory Structure

Because of response limits/timeouts:

Other models (VAR, BVAR, DRNN, SARIMA, ARIMAX, ARDL, RF, XGBoost, utils) will be requested later.

Create a standalone file config.py that defines the CONFIG dictionary for all models.

It should look like this:

All model files (model_xxx.py), utils.py, and run_all_models.py must import CONFIG from config.py.



