# Prompt & Plan Workbench

A Streamlit system for constructing, evaluating, and selectively improving either:

- an LLM prompt, or
- an end-to-end plan for something you intend to build.

The app loads `../MAIN_PROMPT.md` fresh for every evaluation and rewrite. It does
not copy the rubric into this folder, so future edits to the canonical file take
effect immediately.

## What it does

1. Interviews you one question at a time to turn a rough goal into a complete
   prompt or plan, governed by `../CONSTRUCTOR_PROMPT.md`.
2. Hands the draft and distilled usage context directly to the evaluator.
3. Evaluates all nine criteria in `MAIN_PROMPT.md`.
4. Computes a deterministic score from `yes`, `partial`, `no`, and
   `not_applicable` statuses.
5. Proposes independent improvements with priority, rationale, and a preview.
6. Lets you tick only the improvements you approve.
7. Applies only those selections in a second model call.
8. Shows the revised content, a unified diff, an applied-change receipt, and
   downloads for the optimized content and evaluation JSON.

The source prompt or plan is never overwritten.

## Run it

From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your-key"
streamlit run app.py
```

You can instead export `ANTHROPIC_API_KEY`, or choose a provider and enter a key
in the app sidebar. Keys typed in the UI remain in Streamlit session memory and
are not saved by this project.

## Test it

The engine tests do not call an external model:

```bash
python3 -m unittest discover -s tests -v
```

## Files

- `app.py` — UI and interaction state
- `pages/1_Constructor.py` — adaptive interview UI and evaluator handoff
- `engine.py` — live governing-prompt loading, provider calls, response validation,
  scoring, and constrained rewriting
- `tests/test_engine.py` — deterministic unit tests
