# `config/__init__.py` explained

**Last updated:** 2026-08-24  
**Source lines:** 65

Defines the single `Settings` object (a `pydantic-settings` `BaseSettings`) that every other module in the package reads configuration from, plus a process-wide cached accessor `get_settings()`.

## `PROJECT_ROOT`

`Path(__file__).resolve().parents[3]` — climbs from this file (`src/consequence_radar/config/__init__.py`) up three parents to the repository root. This is positional and brittle: if this file were ever moved a directory deeper or shallower, `PROJECT_ROOT` silently points somewhere else with no error, only a wrong `.env` file being read and a wrong default database path. It's used both for locating `.env` and as the base of `database_url`'s default.

Because the actual project directory name is `Consequence And What if?`, `PROJECT_ROOT` — and therefore the default `database_url` below — contains a literal `?`. That's why `storage/__init__.py` cannot let SQLAlchemy parse `sqlite:///`-prefixed URLs directly and instead uses a custom DB-API connection creator (see that file's `.explained.md` and `storage/test_storage.py`'s `test_path_with_question_mark_roundtrips`).

## `Settings` fields

Config: `env_file=PROJECT_ROOT / ".env"`, `extra="ignore"`. No `env_prefix` is set, so every field is read from a bare, unprefixed environment variable name (uppercased field name, e.g. `DATABASE_URL`, `GEMINI_API_KEY`) — there's no namespacing, so an unrelated ambient env var with a matching name (e.g. a stray `DATABASE_URL` set for another tool on the same machine) would silently override the default. Precedence follows pydantic-settings' standard order: explicit constructor kwargs > environment variables > `.env` file values > field defaults. This is why `conftest.py`'s `Settings(database_url=..., report_min_words=..., report_max_words=...)` reliably wins over anything in a local `.env`.

| Field | Type | Default | Notes |
|---|---|---|---|
| `database_url` | `str` | `sqlite:///{PROJECT_ROOT}/data/consequence_radar.db` | Absolute path by construction. `alembic.ini` at the repo root instead hardcodes the **relative** `sqlite:///data/consequence_radar.db` — the two only resolve to the same file when Alembic is invoked with the project root as the working directory. |
| `web_host` | `str` | `"127.0.0.1"` | |
| `web_port` | `int` | `8010` | Bounded `1024–65535` via `Field(ge=..., le=...)`. |
| `gemini_api_key` | `str \| None` | `None` | |
| `google_api_key` | `str \| None` | `None` | Alternate env var name for the same credential; see `api_key` property below. |
| `fast_model` | `str` | `"gemini-2.5-flash"` | |
| `reasoning_model` | `str` | `"gemini-2.5-pro"` | |
| `report_model` | `str` | `"gemini-2.5-pro"` | |
| `max_research_cycles` | `int` | `3` | Bounded `1–10`. |
| `max_graph_nodes` | `int` | `24` | Bounded `3–100`. |
| `max_graph_edges` | `int` | `36` | Bounded `2–200`. |
| `max_research_tasks_per_cycle` | `int` | `8` | Bounded `1–30`. |
| `max_search_queries_per_run` | `int` | `30` | Bounded `1–200`. |
| `enable_url_context_search` | `bool` | `True` | Controls whether grounded-search calls add Gemini URL Context beside Google Search (L28–31). It changes search-call cost and snippet quality, but never changes the controlled-fetch text used for exact-passage verification. |
| `max_fetched_sources_per_run` | `int` | `50` | Bounded `1–200`. |
| `max_model_calls_per_run` | `int` | `45` | Bounded `1–100`. Inline comment explains the number: a full run issues roughly 20 generation calls (selection, initial graph, up to 3 research cycles × up to 4, quantification, review, challenge, adjudication, case selection, report, plus a parse-retry margin). Nothing in code enforces that this default actually stays consistent with that arithmetic if a pipeline stage is added later — it's a comment, not a computed value. Grounded search calls are metered separately via `max_search_queries_per_run`, not against this budget. |
| `max_wall_time_seconds` | `int` | `1800` | Bounded `10–7200`. |
| `max_output_tokens` | `int` | `32768` | Bounded `1024–65536`. Per-call provider argument, not tracked/enforced by `metering.UsageLedger` as a cumulative budget. |
| `report_context_token_budget` | `int` | `24000` | Bounded `≥1000`, no upper bound. Not cross-checked against `max_output_tokens`. |
| `report_min_words` | `int` | `800` | Bounded `≥100`. |
| `report_max_words` | `int` | `1200` | Bounded `≥200`. |
| `worker_count` | `int` | `2` | Bounded `1–8`. |
| `fetch_timeout_seconds` | `float` | `12.0` | Bounded `1–60`. |
| `fetch_max_bytes` | `int` | `1_500_000` | Bounded `10,000–10,000,000`. |
| `fetch_redirect_limit` | `int` | `4` | Bounded `0–10`. |
| `fetch_retry_limit` | `int` | `1` | Bounded `0–3`. |

## `coherent_report_bounds` validator

A `model_validator(mode="after")` that rejects construction if `report_min_words > report_max_words`. The comment explains why this exists as an explicit check rather than relying on the individual `ge`/`le` bounds: each bound is independently plausible (min ≥100, max ≥200), so an inverted pair (e.g. min=1200, max=800) would otherwise pass startup validation cleanly and only fail much later, at the report-writing stage, when no article could satisfy an impossible word-count constraint. This is the *only* cross-field validation in the class — nothing similarly checks, for example, `report_context_token_budget` against `max_output_tokens`, or the research-cycle/task-count fields against `max_model_calls_per_run`.

## `api_key` property

Returns `gemini_api_key or google_api_key` — lets either env var name supply the credential, with `gemini_api_key` taking precedence if both are set. Consumers (`providers/model/__init__.py`, `providers/search/__init__.py`, `web/app.py`) check `bool(settings.api_key)`; when both are `None`, those call sites raise or show a "not configured" state rather than this file doing so — `config/__init__.py` itself never validates that a key is present.

## `get_settings()`

`@lru_cache`-wrapped zero-argument factory returning `Settings()`. Because it's cached for the life of the process, changing an environment variable mid-process has no effect on later `get_settings()` calls — the cache must be cleared (or `Settings(...)` constructed directly, bypassing the cache) to pick up a change. This is exactly why tests construct `Settings(...)` explicitly instead of calling `get_settings()`.

## Connections

`consequence_radar.config` (either the `Settings` class or `get_settings`) is imported by `research/__init__.py`, `pipeline/__init__.py`, `pipeline/test_budget.py`, `web/app.py`, `graph/__init__.py`, and `challenge/__init__.py` — i.e. essentially every stage of the pipeline plus the web entry point reads its tunables from here. It does not import from any other `consequence_radar` submodule, keeping it a leaf dependency.
