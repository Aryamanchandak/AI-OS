# bridge

Connects `prompt_plan_workbench` and `veritas` without either project
importing or knowing about the other. Everything here is disposable —
`rm -rf bridge/` removes all trace of the connection; neither sibling
project is edited by anything in this folder.

Two independent things live here:

## 1. Align mode — improve Veritas's own prompts

Veritas's master system prompt (`../PROMPT.md`) and its nine skill
contracts (`../veritas/prompts/*.md`) are exactly what the workbench's
9-criterion rubric is built to grade. `align.py` reads one of them,
runs it through the workbench's evaluator + rewriter, and writes a
**candidate + diff** to `out/` — it never edits `veritas/` itself.

```
python bridge/align.py --target master
python bridge/align.py --target decompose --select all
```

`--target` accepts `master` or any LLM skill name from
`veritas/config.yaml` (decompose, search, extract, grade, synthesize,
verify, compose, scope, compose_topic). `--select high` (default)
applies only high-priority improvements, matching the workbench UI's
default; `--select all` applies everything proposed.

Review `out/<target>.diff` and `out/<target>.evaluation.json`. If you
like the candidate:

```
python bridge/apply.py --target master
```

This backs up the live file first (`PROMPT.md.bak.<timestamp>`) and
overwrites it with the candidate. Revert any time with the `cp`
command it prints.

## 2. Subject mode — send a claim/topic to Veritas

`send_subject.py` is a thin pass-through to `veritas/cli.py` — it does
**not** run the rubric evaluator, because a one-line claim doesn't have
a "conversation loop" or "tool separation" to grade against. For
anything beyond a clean one-liner, draft it with the workbench's
**Constructor** page first (`streamlit run prompt_plan_workbench/app.py`,
then the Constructor tab), then hand the result here:

```
python bridge/send_subject.py "Creatine supplementation improves cognitive performance in sleep-deprived adults"
python bridge/send_subject.py --topic "How does intermittent fasting affect metabolic health?"
```

## Requirements

Runs from the assignment root's Python environment; needs whatever
`prompt_plan_workbench/requirements.txt` needs (for align mode) plus an
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in the environment (or pass
`--provider`/`--model`/`--api-key`).

## Deleting this

`rm -rf bridge/`. Nothing in `prompt_plan_workbench/` or `veritas/`
references this folder.
