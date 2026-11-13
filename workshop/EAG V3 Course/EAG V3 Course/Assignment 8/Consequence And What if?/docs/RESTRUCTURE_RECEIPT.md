# Changes receipt — vertical-slice restructure

**Date:** 2026-08-22
**Requested by:** isolate each pipeline component into its own folder for individual inspection.
**Result:** 63/63 tests passing, wheel builds clean (prompts included, tests excluded).

## Summary

`src/consequence_radar/` was a flat list of 16 module files plus a `providers/` folder of 3 more, with all tests centralized under `tests/unit/` (several files covering two or three modules at once) and all 10 LLM prompts centralized under a flat `prompts/` directory. Every pipeline stage is now its own folder containing its source, its unit test(s), and its prompt(s) together.

## Before → after

```
Before                              After
src/consequence_radar/              src/consequence_radar/
  cases.py                            cases/
  challenge.py                          __init__.py
  config.py                             case_selector.md
  deduplicate.py                        test_cases.py
  evidence.py                         challenge/
  graph.py                              __init__.py
  ingest.py                             adjudicator.md
  metering.py                           challenger.md
  models.py                             whole_graph_reviewer.md
  pipeline.py                         config/__init__.py
  quantify.py                         deduplicate/{__init__.py, test_deduplicate.py}
  report.py                           evidence/{__init__.py, test_evidence.py}
  report_context.py                   graph/
  research.py                           __init__.py
  select.py                             graph_patcher.md
  storage.py                            initial_graph_builder.md
  providers/                            test_graph.py
    model.py                          ingest/{__init__.py, test_ingest.py}
    fetch.py                          metering/{__init__.py, test_metering.py}
    search.py                         models/{__init__.py, test_models.py}
  web/ (unchanged)                    pipeline/{__init__.py, test_budget.py}
                                       providers/
prompts/                                model/{__init__.py, test_model.py}
  case_selector.md                      fetch/{__init__.py, test_fetch.py}
  adjudicator.md                        search/__init__.py
  challenger.md                       quantify/{__init__.py, test_quantify.py}
  whole_graph_reviewer.md             report/{__init__.py, newsletter_writer.md, test_report.py}
  graph_patcher.md                    report_context/{__init__.py, test_report_context.py}
  initial_graph_builder.md            research/
  newsletter_writer.md                  __init__.py
  candidate_selector.md                 gap_analyser.md
  gap_analyser.md                       claim_extractor.md
  claim_extractor.md                  select/{__init__.py, candidate_selector.md}
                                       storage/{__init__.py, test_storage.py}
tests/unit/                           web/ (unchanged)
  test_cases_report.py       (split)
  test_evidence_quantify.py  (split)
  test_models_storage.py     (split)
  test_fetch_ingest.py       (split)
  test_graph.py              (moved)
  test_metering.py           (moved)
  test_model_provider.py     (moved)
  test_run_budget.py         (moved)
  test_generated_bounds.py   (kept — spans config + models)
  test_regressions.py        (kept — spans 9 modules)
tests/conftest.py             (moved to repo root)
```

## What moved where

| Old file | New location(s) |
|---|---|
| `cases.py` | `cases/__init__.py` |
| `challenge.py` | `challenge/__init__.py` |
| `config.py` | `config/__init__.py` |
| `deduplicate.py` | `deduplicate/__init__.py` |
| `evidence.py` | `evidence/__init__.py` |
| `graph.py` | `graph/__init__.py` |
| `ingest.py` | `ingest/__init__.py` |
| `metering.py` | `metering/__init__.py` |
| `models.py` | `models/__init__.py` |
| `pipeline.py` | `pipeline/__init__.py` |
| `quantify.py` | `quantify/__init__.py` |
| `report.py` | `report/__init__.py` |
| `report_context.py` | `report_context/__init__.py` |
| `research.py` | `research/__init__.py` |
| `select.py` | `select/__init__.py` |
| `storage.py` | `storage/__init__.py` |
| `providers/model.py` | `providers/model/__init__.py` |
| `providers/fetch.py` | `providers/fetch/__init__.py` |
| `providers/search.py` | `providers/search/__init__.py` |
| `prompts/case_selector.md` | `cases/case_selector.md` |
| `prompts/challenger.md` | `challenge/challenger.md` |
| `prompts/adjudicator.md` | `challenge/adjudicator.md` |
| `prompts/whole_graph_reviewer.md` | `challenge/whole_graph_reviewer.md` |
| `prompts/graph_patcher.md` | `graph/graph_patcher.md` |
| `prompts/initial_graph_builder.md` | `graph/initial_graph_builder.md` |
| `prompts/newsletter_writer.md` | `report/newsletter_writer.md` |
| `prompts/candidate_selector.md` | `select/candidate_selector.md` |
| `prompts/gap_analyser.md` | `research/gap_analyser.md` |
| `prompts/claim_extractor.md` | `research/claim_extractor.md` |
| `tests/conftest.py` | `conftest.py` (repo root) |
| `tests/unit/test_graph.py` | `graph/test_graph.py` |
| `tests/unit/test_metering.py` | `metering/test_metering.py` |
| `tests/unit/test_model_provider.py` | `providers/model/test_model.py` |
| `tests/unit/test_run_budget.py` | `pipeline/test_budget.py` |
| `tests/unit/test_cases_report.py` | split → `cases/test_cases.py`, `report_context/test_report_context.py`, `report/test_report.py` |
| `tests/unit/test_evidence_quantify.py` | split → `evidence/test_evidence.py`, `quantify/test_quantify.py` |
| `tests/unit/test_models_storage.py` | split → `models/test_models.py`, `storage/test_storage.py` |
| `tests/unit/test_fetch_ingest.py` | split → `providers/fetch/test_fetch.py`, `ingest/test_ingest.py`, `deduplicate/test_deduplicate.py` |

**Left in place, deliberately:** `tests/unit/test_regressions.py` (spans cases, config, evidence, models, providers.fetch, report, report_context, storage, web.app) and `tests/unit/test_generated_bounds.py` (spans config + models) — both are genuine cross-component regression suites; forcing them into one component's folder would misrepresent what they test. `tests/integration/test_pipeline.py` and `tests/integration/test_api.py` stay in `tests/integration/` for the same reason. `tests/evaluation/` and `tests/fixtures/` are untouched.

## Code changes required to keep it working

1. **Relative-import depth** — every converted `module.py` → `module/__init__.py` sits one directory deeper, so its own `from .x import y` became `from ..x import y` (and `providers/model|fetch|search`, already one level nested, went from `..x` to `...x`).
2. **`config/__init__.py`** — `PROJECT_ROOT = Path(__file__).resolve().parents[2]` → `parents[3]` (one more directory between the file and the repo root).
3. **`providers/model/__init__.py`** — `load_prompt()`'s base path changed from `PROJECT_ROOT / "prompts" / name` to `PROJECT_ROOT / "src" / "consequence_radar" / name`.
4. **13 `prompt_name=` call sites** across `cases`, `challenge` (×3), `graph` (×2), `report`, `select`, `research` (×2), and `pipeline` (×3, referencing `graph/graph_patcher.md` cross-folder) updated to the new component-relative paths, e.g. `"case_selector.md"` → `"cases/case_selector.md"`.
5. **`tests/evaluation/test_frozen_fixtures.py`** — its prompt-injection check globbed the old flat `prompts/*.md`; updated to `(root/"src/consequence_radar").glob("**/*.md")` with an explicit `assert prompt_files, "no prompt files found"` so a bad path fails loudly instead of silently passing on zero matches.
6. **`pyproject.toml`** — `testpaths` widened from `["tests"]` to `["src/consequence_radar", "tests"]` so pytest discovers the relocated component tests; added `exclude = ["**/test_*.py"]` under `[tool.hatch.build.targets.wheel]` so test files don't ship in the built package (prompts, being `.md`, still do).
7. **`docs/ARCHITECTURE.md`** — updated the one reference to `pipeline.py` and the flat `prompts/` layout to describe the new per-component folder structure.

## What did *not* change

- `web/` — already a self-contained folder (`app.py` + `static/` + `templates/`); left as-is.
- `__init__.py`, `__main__.py`, `providers/__init__.py`, `web/__init__.py`, `web/app.py` — no relative-import depth change since these files didn't move.
- Public import paths — `from consequence_radar.cases import ...` etc. still work unchanged everywhere outside the package (`migrations/env.py`, `web/app.py`, all test files that weren't split) because Python treats a package (`cases/__init__.py`) the same as a module (`cases.py`) from the outside.
- Runtime behavior, model prompts' content, and the CLI entry point (`consequence-radar = "consequence_radar.web.app:run"`).

## Verification performed

- `./radar test` after each of the four phases (conftest+config move → source restructure → prompt relocation → test split), so any failure would localize to one class of change. All phases green.
- Final run: **63 passed** (up from 62 — splitting `test_context_and_invalid_citation_fail_closed` into a `report_context` budget test and a `report` citation test added one test function).
- Manually loaded all 10 relocated prompts through `load_prompt()` to confirm the new path resolution works.
- Built the wheel (`uv build --wheel`) and inspected its contents: 0 `test_*.py` files, all 10 `.md` prompts present.
