---
name: per-file-explained-md-docs-2026-08-23
description: Every source file in src/consequence_radar/ (plus radar and conftest.py) has a companion <name>.<ext>.explained.md doc written 2026-08-23.
type: project
---

On 2026-08-23, per-file explanatory docs were written for all 54 in-scope source files in this project: every `.py` file under `src/consequence_radar/` (including each package's `__init__.py`, which holds real logic, and its `test_*.py` sibling), the web layer (`web/app.py`, `web/static/app.js`, `web/static/styles.css`, `web/templates/*.html`), every LLM agent prompt `.md` file (`cases/case_selector.md`, `challenge/adjudicator.md`, `challenge/challenger.md`, `challenge/whole_graph_reviewer.md`, `graph/graph_patcher.md`, `graph/initial_graph_builder.md`, `report/newsletter_writer.md`, `research/claim_extractor.md`, `research/gap_analyser.md`, `select/candidate_selector.md`), and the root-level `radar` script and `conftest.py`.

**Why:** The user wanted a focused explanatory doc sitting next to every source file (distinct from `docs/ARCHITECTURE.md`, `docs/EVALUATION.md`, `overview/overview.md`, which already cover system-level architecture and were explicitly not to be duplicated).

**How to apply:** The naming convention is `<name>.<ext>.explained.md` in the SAME directory as the source file (e.g. `src/consequence_radar/models/__init__.py` -> `src/consequence_radar/models/__init__.py.explained.md`; `radar` -> `radar.explained.md`). If asked to update docs after a code change, find the matching `.explained.md` next to the changed file and update it rather than creating a new doc or writing to a `deep-dive/` folder — this project does NOT use the deep-dive/ convention from the default code-archaeologist template. See also [[project__known-bug-apply-patch-import-2026-08-23]] for a live bug surfaced while writing these docs.
