

run_all_models.py 

- Add recency weighting 





run_test.py 



RUN_ALL_MODELS.PY



Nice — I’ll break the full refactor into a small set of implementable groups you can tackle one-by-one.

Each group contains what to change, exact files / functions to edit, step-by-step tasks, tests to write, risks, and acceptance criteria. I order them by priority (what must be fixed first to avoid breaking runs) and include a short effort estimate so you can plan work sprints.

I assume you want to implement these changes in the repo layout and API we discussed earlier (split modules: data_prep.py, training.py, tuning.py, stacking.py, orchestrator.py, scalers/boxcox_revin.py already present). If you want I can produce starter code for any group next.

Why first: fixes prevent crashes and inconsistent logging that will block all further work.

Changes (exact):

Files / functions to edit:

Step-by-step tasks:

Tests:

Risks: none if done before tuning loops run.

Acceptance criteria:

Effort: 0.25–0.5 person-days.

Why next: many bugs (double inverse, DRNN leakage, RevIN) stem from inconsistent scaler APIs. Fixing scalers first enables safe model changes.

Changes (exact):

Files / functions to edit:

Step-by-step tasks:

Tests:

Risks: BoxCox RevIN API may not match expected wrapper—check its methods and adapt wrapper accordingly.

Acceptance criteria:

Effort: 1.0–2.0 person-days.

Why: many bugs and fragile behavior come from heterogeneous model module interfaces.

Changes (exact):

Files / functions to edit:

Step-by-step tasks:

Tests:

Risks: existing model modules may have subtle signature differences. Adapter layer will expose these mismatches early.

Acceptance criteria:

Effort: 1.0–2.0 person-days.

Why: must centralise inverse transforms and return only original-scale preds; otherwise downstream aggregates are wrong.

Changes (exact):

Files / functions to edit:

Step-by-step tasks:

