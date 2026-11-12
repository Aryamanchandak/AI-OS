

Executive Summary

This is an enterprise-grade, production-ready CPI (Consumer Price Index)

forecasting system built for ICICI Prudential. The codebase represents a

sophisticated multi-model ensemble architecture with approximately 27,638 lines

of Python code across 84MB of data and models. The system demonstrates advanced

ML engineering practices with temporal causality enforcement, hyperparameter

optimization, and model explainability.

1. Project Architecture Overview

1.1 High-Level Structure

CPI Project 4/Data/Models/

├── Orchestrator & Run Models Py/ (~20,070 LOC) - Core orchestration

├── Individual Models Py/ (~7,568 LOC) - 11 model implementations

├── Individual Data Train Files Py/ - Dataset-specific training scripts

├── Data Excel/ (~29MB) - Raw CPI data (9 inflation

measures)

├── outputs/ (~1.6MB) - Predictions & metrics

└── Supporting directories (JSON, logs, PKL files)

1.2 Code Distribution

| Component | Lines of Code | Purpose

|

|-----------------------|---------------|----------------------------------------

| Orchestrator Layer | 20,070 | Data pipeline, training, ensemble logic

|

| Model Implementations | 7,568 | 11 ML/statistical models

|

| Total Python Code | ~27,638 | Comprehensive forecasting system

|

2. Core Architecture Components

2.1 Configuration System (config.py - 364 lines)

Strengths:

Key Features:

# 9 distinct inflation measures tracked

TARGET_COLS = {

'clothing_footwear', 'core_inflation_ex_food_fuel',

'food_beverage', 'fuel_light', 'housing', 'misc',

'pan_tobacco_intoxicants', 'headline_sub', 'headline_sub_sub'

}

# Model-specific scalers for optimal performance

MODEL_SCALERS = {

'ARDL/ARIMAX/SARIMA/BVAR/VAR': 'minmax_rolling', # Statistical

'RF/XGBoost/DRNN_*/KAN': 'causal_boxcox_revin' # ML/DL

}

Configuration Highlights:

2.2 Data Pipeline (data.py - 1,227 lines)

Architecture:

Preprocessing Pipeline:

Raw CPI Data → Quarterly→Monthly Conversion → Exogenous Merge →

Lag Feature Engineering (24 lags) → Train/Test Split → Output

Advanced Features:

1. Quarterly to Monthly Conversion: Forward-fills quarterly data (e.g., RBI

consumer confidence surveys)

2. Exogenous Variable Integration:

3. Lag Engineering: Creates 24-month historical lags for all features

4. Oil Exclusion Logic: Removes oil columns for core_inflation_ex_food_fuel

dataset

Data Files Located:

Data/Models/Data Excel/ contains:

2.3 Model Implementations (11 Models)

The system implements 11 distinct forecasting models with Blueprint v3.4

compliance:

Statistical Models (5)

1. ARDL (AutoRegressive Distributed Lag) - 17,977 bytes

2. ARIMAX - 21,563 bytes

3. SARIMA - 21,729 bytes

4. BVAR (Bayesian VAR) - 21,415 bytes

5. VAR (Vector Autoregression) - 25,173 bytes

