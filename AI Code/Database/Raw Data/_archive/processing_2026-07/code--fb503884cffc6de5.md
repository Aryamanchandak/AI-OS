errors 

get rid of the type of messages below 



1-07 10:58:58,293 - scaler_rolling_hybrid - WARNING - 'toilet soap': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,293 - scaler_rolling_hybrid - WARNING - 'toothpaste; toothbrush; comb; etc.': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,294 - scaler_rolling_hybrid - WARNING - 'powder; snow; cream; lotion and perfume': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,294 - scaler_rolling_hybrid - WARNING - 'hair oil; shampoo; hair cream': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,294 - scaler_rolling_hybrid - WARNING - 'shaving blades; shaving stick; razor': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,295 - scaler_rolling_hybrid - WARNING - 'shaving cream; aftershave lotion': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,295 - scaler_rolling_hybrid - WARNING - 'sanitary napkins': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,295 - scaler_rolling_hybrid - WARNING - 'clock; watch': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,295 - scaler_rolling_hybrid - WARNING - 'suitcase; trunk; box; handbag and other travel goods': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,296 - scaler_rolling_hybrid - WARNING - 'umbrella; raincoat': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,296 - scaler_rolling_hybrid - WARNING - 'any other personal goods': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,296 - scaler_rolling_hybrid - WARNING - 'gold': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,297 - scaler_rolling_hybrid - WARNING - 'silver': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,297 - scaler_rolling_hybrid - WARNING - 'other ornaments': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,297 - scaler_rolling_hybrid - WARNING - 'barber; beautician; etc.': 0 values below 0, 2 values above 1
2025-11-07 10:58:58,298 - scaler_rolling_hybrid - WARNING - 'Historical Core Inflation ex Food, fuel, petrol, diesel, Gold': 0 values below 0, 2 valu



here there is only 3, when there should be as there are 4 targets. Importantly I dont want you to compare against actual just show predictions 


another issue is that you should take the last 2 rows and predict for the months shead from that point, assuming that is the last data point. How can you have the actual value for that, when it isnt in the dataset, predict for the months ahead. 



2025-11-07 10:58:58,307 - main - INFO -   2025-05: Actual=191.2449
2025-11-07 10:58:58,307 - main - INFO -     (Ensemble prediction requires running all 4 models - placeholder)
2025-11-07 10:58:58,307 - main - INFO -   2025-06: Actual=191.5616
2025-11-07 10:58:58,307 - main - INFO -     (Ensemble prediction requires running all 4 models - placeholder)
2025-11-07 10:58:58,307 - main - INFO -
2025-11-07 10:58:58,308 - main - INFO -
core_ex_mobile_tariffs:
2025-11-07 10:58:58,308 - main - INFO - ============================================================
2025-11-07 10:58:58,325 - main - INFO - Using ensemble model for predictions:
2025-11-07 10:58:58,325 - main - INFO -   Note: This is a post-training validation check on in-sample data

2025-11-07 10:58:58,325 - main - INFO -   2025-05: Actual=191.8401
2025-11-07 10:58:58,325 - main - INFO -     (Ensemble prediction requires running all 4 models - placeholder)
2025-11-07 10:58:58,325 - main - INFO -   2025-06: Actual=192.1575
2025-11-07 10:58:58,325 - main - INFO -     (Ensemble prediction requires running all 4 models - placeholder)
2025-11-07 10:58:58,325 - main - INFO -
2025-11-07 10:58:58,326 - main - INFO -
headline:
2025-11-07 10:58:58,326 - main - INFO - ============================================================
2025-11-07 10:58:58,341 - main - INFO - Using ensemble model for predictions:
2025-11-07 10:58:58,341 - main - INFO -   Note: This is a post-training validation check on in-sample data

2025-11-07 10:58:58,342 - main - INFO -   2025-05: Actual=193.0000
2025-11-07 10:58:58,342 - main - INFO -     (Ensemble prediction requires running all 4 models - placeholder)
2025-11-07 10:58:58,342 - main - INFO -   2025-06: Actual=194.2000
2025-11-07 10:58:58,342 - main - INFO -     (Ensemble prediction requires running all 4 models - placeholder)
2025-11-07 10:58:58,342 - main - INFO -





also help solve the below temporal violation error 



2025-11-07 10:58:30,892 - main - INFO -     Optimizing rolling window for ARDL...
2025-11-07 10:58:30,892 - main - INFO -     Testing 34 window sizes: [6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72]
2025-11-07 10:58:30,957 - main - INFO -     Top 3 windows: 72mo (0.1127), 54mo (0.1146), 64mo (0.1155)
2025-11-07 10:58:30,957 - main - INFO -     ✓ Selected optimal window: 72 months (RMSE=0.1127)
2025-11-07 10:58:30,958 - main - INFO -     Using tuned hyperparameters for ARDL
2025-11-07 10:58:30,959 - main - ERROR -     ARDL: ✗ ERROR: ❌ TEMPORAL VIOLATION: Cannot predict on/before training data!
train_end_date: 2022-12-31
predict_date:   2022-10-31
This violates Blueprint v3.4 causality constraint.
2025-11-07 10:58:30,960 - main - INFO -     Optimizing rolling window for ARIMAX...
2025-11-07 10:58:30,960 - main - INFO -     Testing 34 window sizes: [6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72]
2025-11-07 10:58:31,024 - main - INFO -     Top 3 windows: 72mo (0.1127), 54mo (0.1146), 64mo (0.1155)
2025-11-07 10:58:31,024 - main - INFO -     ✓ Selected optimal window: 72 months (RMSE=0.1127)
2025-11-07 10:58:31,024 - main - INFO -     Using tuned hyperparameters for ARIMAX
2025-11-07 10:58:31,179 - main - ERROR -     ARIMAX: ✗ ERROR: ❌ TEMPORAL VIOLATION: Cannot predict on/before training data!
train_end_date: 2022-12-31
predict_date:   2022-10-31
This violates Blueprint v3.4 causality constraint.
2025-11-07 10:58:31,179 - main - INFO -     Optimizing rolling window for SARIMA...
2025-11-07 10:58:31,179 - main - INFO -     Testing 34 window sizes: [6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72]
2025-11-07 10:58:32,228 - main - INFO -     Top 3 windows: 42mo (0.1160), 40mo (0.1252), 44mo (0.1276)
2025-11-07 10:58:32,228 - main - INFO -     ✓ Selected optimal window: 42 months (RMSE=0.1160)
2025-11-07 10:58:32,239 - main - INFO -     Using tuned hyperparameters for SARIMA
2025-11-07 10:58:39,616 - main - INFO -     SARIMA: ✓ R²=0.3718, RMSE=0.3042
2025-11-07 10:58:39,621 - main - INFO -     Optimizing rolling window for BVAR...
2025-11-07 10:58:39,621 - main - INFO -     Testing 34 window sizes: [6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72]
2025-11-07 10:58:39,749 - main - INFO -     Top 3 windows: 72mo (0.1127), 54mo (0.1146), 64mo (0.1155)
2025-11-07 10:58:39,749 - main - INFO -     ✓ Selected optimal window: 72 months (RMSE=0.1127)
2025-11-07 10:58:39,750 - main - INFO -     Using tuned hyperparameters for BVAR
2025-11-07 10:58:39,751 - main - ERROR -     BVAR: ✗ ERROR: ❌ TEMPORAL VIOLATION: Cannot predict on/before training data!
train_end_date: 2022-12-31
predict_date:   2022-10-31
This violates Blueprint v3.4 causality constraint.
2025-11-07 10:58:39,752 - main - INFO -     Optimizing rolling window for VAR...
2025-11-07 10:58:39,752 - main - INFO -     Testing 34 window sizes: [6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72]
2025-11-07 10:58:41,138 - main - INFO -     Top 3 windows: 42mo (0.1160), 40mo (0.1252), 44mo (0.1276)
2025-11-07 10:58:41,139 - main - INFO -     ✓ Selected optimal window: 42 months (RMSE=0.1160)
2025-11-07 10:58:41,152 - main - INFO -     Using tuned hyperparameters for VAR

=== VAR Model ===





