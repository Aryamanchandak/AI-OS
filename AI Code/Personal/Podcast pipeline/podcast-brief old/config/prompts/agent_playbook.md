# podcast-brief MCP Agent Playbook

## Two modes

### 1. Automation (default) — `generate_brief(url)`
Runs the complete pipeline in a single tool call: ingest → transcribe → extract → research → synthesize → deliver.
Stage order is enforced in Python code, never by the model. Use this unless you need to pause between stages.

### 2. Step-by-step — per-stage tools
Call each tool in the canonical order below when you want to inspect outputs between stages.

## Canonical stage order

1. `ingest_audio(url, show_name?, profile?)` → returns `episode_id`
2. `transcribe_episode(episode_id, speakers_hint?)` → returns duration/speakers
3. `extract_claims(episode_id)` → returns claim count and types
4. `research_claims(episode_id)` → returns surfaced item counts (skip if not needed)
5. `synthesize_brief(episode_id)` → returns brief path and char count
6. `deliver_brief(episode_id)` → returns reader_url

## Verification gate

**After each per-stage tool, call `get_episode_status(episode_id)` and confirm the expected `runs` row has `status = "completed"` before proceeding to the next stage.** The `runs` log is the authoritative record of what has actually completed.

## Verifying claims

`research_claims` runs each extracted claim through Research_MCP triage and source-gathering.
Results are persisted in `data/research_items/<episode_id>.json` and include, per claim:
- `triage_correctness`: `"true"` | `"false"` | `"topic"` (off-topic / neither true nor false)
- `triage_confidence`: 0.0–1.0
- `logical_sources`: list of supporting/contradicting sources with titles, authors, and URLs

Read the full brief via the `brief://{episode_id}` resource without re-running the pipeline.

## Admin tools

- `list_recent_episodes(limit?)` — check what's been processed
- `list_shows()` — see configured shows
- `check_config()` — verify API keys and token validity
- `poll_shows(limit_per_show?, dry_run?)` — check for new RSS/YouTube episodes
