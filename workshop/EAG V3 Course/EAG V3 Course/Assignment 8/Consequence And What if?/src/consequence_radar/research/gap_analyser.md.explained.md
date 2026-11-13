# `research/gap_analyser.md`

Five-line system prompt that opens each research cycle by inspecting the current causal graph and proposing what still needs to be researched.

## Role in the pipeline
Consumed by `generate_tasks()` in `research/__init__.py`, called at the start of every research cycle in the pipeline. It is the only decision-maker for what gets searched next — everything downstream (`retrieve_for_tasks`, `extract_claims`) just executes on whatever `ResearchTask`s this prompt proposes.

## Expected inputs
`generate_tasks()` sends the entire `CausalGraph` as raw JSON (`graph.model_dump_json()`) — nothing else; no claims, no prior task history, no run settings are included in the payload itself (though `settings.max_research_tasks_per_cycle` is applied afterward in Python, not communicated to the model).

The prompt sets a priority order for what to target: factual premise first, then load-bearing mechanisms, Indian company/sector exposure, quantities needed for a concrete endpoint, material assumptions, counterevidence, and background last. It requires queries that "seek sources, not presume the answer" (i.e. not leading/loaded search strings), explicitly calls for counterevidence tasks when the graph lacks any, and — like the challenge prompts — requires facts/forecasts/assumptions/inferences/estimates to stay classified distinctly. Critically, it defines a legitimate "nothing to do" condition: return no tasks when the hypothesis is already adequately supported, quantified or explicitly directional, challenged, and reaches a concrete Indian-equity endpoint — an empty `tasks` list is a valid, expected output, not a failure.

## Demanded output format
Structured JSON matching `ResearchTaskList` (`{"tasks": [ResearchTask, ...]}`), enforced via `response_json_schema`. Each `ResearchTask` has `id`, `target_type` (`edge`/`assumption`/`estimate`/`entity`/`whole_graph`), `target_id` ("use only existing target IDs" per the prompt), `question`, `intent` (one of seven literals like `confirm_premise`, `quantify`, `find_counterevidence`), `preferred_source_types`, `search_queries`, and `priority` (low/medium/high).

## Downstream consumer
`generate_tasks()` does no validation of `target_id` against the actual graph (unlike, say, `select_candidate` checking `source_item_ids` against supplied extracts) — it trusts the returned tasks, sorts them by a hardcoded priority map (`high` < `medium` < `low`), and truncates the list to `settings.max_research_tasks_per_cycle` (default 8). The surviving `ResearchTask`s feed straight into `retrieve_for_tasks`, which reads each task's `search_queries` to drive actual web searches, and later into `extract_claims`, which includes the task list in the claim-extraction prompt payload so the model can stay "focused on the named graph tasks."
