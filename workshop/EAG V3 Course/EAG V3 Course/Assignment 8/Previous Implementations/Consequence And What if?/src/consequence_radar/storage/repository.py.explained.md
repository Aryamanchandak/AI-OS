# `storage/__init__.py` explained

SQLite-backed persistence for pipeline runs: it defines the ORM schema (`RunRow`, `EventRow`, `ArtifactRow`) and a `Repository` class that is the only way the rest of the codebase reads or writes run state, progress events, and versioned artifacts (graphs, claims, reports).

## Schema

Three SQLAlchemy 2.0 declarative tables, all keyed off a `run_id`:

- **`runs`** — one row per pipeline run. `id` (UUID string, PK), `status` (string, indexed — set from `RunStatus`, e.g. `queued`, `building_graph`, `researching`... see `models/__init__.py`), `batch_json` (the input `NewsBatch` serialized whole), `created_at`/`updated_at`, `error` (nullable text), `warning_count` (int, default 0). Has cascading `events` and `artifacts` relationships.
- **`events`** — append-only progress log. `run_id` FK, `sequence` (per-run monotonic counter), `stage`, `message`, `kind` (default `"progress"`), `created_at`. Unique on `(run_id, sequence)`.
- **`artifacts`** — versioned JSON blobs produced during a run (graph snapshots, claims, the final report). `run_id` FK, `kind` (e.g. `"graph"`, `"claims"`, `"report"`), `artifact_key` (default `"default"`, lets multiple named artifacts of the same `kind` coexist), `version` (int, auto-incremented per `run_id`+`kind`+`key`), `payload_json`. Unique on `(run_id, kind, artifact_key, version)`.

`warning_count` is written once, to `0`, in `create_run`, and read back in `get_run`. Nothing in this file (or, per grep, anywhere else in `src`) ever increments it. It is a dead column as currently wired — the schema anticipates a warning-tracking feature that doesn't exist yet.

## `Repository.__init__(database_url)`

Three branches on the URL:

- `"sqlite:///:memory:"` — uses SQLAlchemy's `StaticPool` with a `sqlite3.connect(":memory:", check_same_thread=False)` creator, so the single in-memory connection is shared across threads/sessions instead of each connection getting its own throwaway DB.
- `"sqlite:///..."` (a real file path) — parses the path with `pathlib`, creates parent directories, and connects via a **custom DB-API `creator` callable** rather than letting SQLAlchemy parse the URL directly. The comment explains why: this project's own path contains a literal `?` (see `config/__init__.py` — `PROJECT_ROOT` is `.../Consequence And What if?`), and `?` is a valid path character on macOS but SQLAlchemy's URL parser treats it as the start of a query string, which would corrupt the path. `test_path_with_question_mark_roundtrips` in `test_storage.py` is the regression test for exactly this.
- Anything else — passed straight to `create_engine` (e.g. a Postgres URL), no special handling.

For SQLite specifically, a `connect` event handler sets `PRAGMA busy_timeout=5000` and `PRAGMA journal_mode=WAL`. The comment is explicit about why: without WAL, a reader (browser polling for status) can block a writer (a run worker) and SQLite raises "database is locked" immediately instead of waiting, which manifested as flaky run failures.

## `init_schema()`

Calls `Base.metadata.create_all(engine)` to create tables if absent, then hand-creates an `alembic_version` table and stamps it `'0001'` if empty. The intent (per the inline comment) is to keep a freshly-`create_all`'d database and one bootstrapped via the Alembic CLI (`migrations/versions/0001_initial.py`) in agreement, so future `alembic upgrade` calls know where they're starting from. This is currently safe only because the migrations directory holds exactly one revision that matches this ORM metadata — the code does not verify that invariant, so if a second Alembic revision is added without updating this file's models (or vice versa), a `create_all`-bootstrapped database would be silently stamped as being one revision behind what its actual shape represents. Nothing here runs the migrations themselves.

## `session()` context manager

Wraps `sessionmaker()` sessions: commits on clean exit, rolls back and re-raises on any exception. Every public method opens its own session via this contextmanager — there is no cross-method transaction support, so e.g. `create_run` followed by `add_event` (see below) are two separate commits, not one atomic unit.

## Public methods

- **`create_run(batch, run_id=None)`** — generates a UUID if none given, inserts a `RunRow` with status `QUEUED` and the batch serialized via Pydantic's `model_dump_json()`, then immediately calls `add_event(run_id, "queued", ...)` as a second, separate transaction. Returns the run id.
- **`set_status(run_id, status, *, error=None)`** — loads the row by PK, raises `KeyError` if missing (the only method in this file that raises on a missing run rather than returning `None`), and unconditionally sets `row.error = error`. Because `error` defaults to `None`, calling `set_status(run_id, "researching")` after an earlier error was recorded **silently clears that error** — there's no append-only error log, just this one mutable field.
- **`add_event(run_id, stage, message, kind="progress")`** — reads the current max `sequence` for the run (`0` if none), inserts at `max+1`. This is a read-then-write race: nothing prevents two concurrent callers for the same `run_id` from reading the same max and colliding on the `UniqueConstraint`, which would raise an uncaught `IntegrityError`. In practice the pipeline runs each run's stages sequentially in one worker, so this is fine under the current single-writer-per-run assumption but would break under concurrent writers to the same run.
- **`save_artifact(run_id, kind, payload, *, key="default", version=None)`** — same read-max-then-insert pattern as `add_event`, auto-versioning if `version` isn't passed explicitly. `payload` is serialized through the module-level `_json()` helper.
- **`artifact(run_id, kind, *, key="default", version=None)`** — fetches one artifact: a specific version if given, otherwise the latest (`ORDER BY version DESC LIMIT 1`). Returns the parsed JSON dict, or `None` if nothing matches — note the inconsistency with `set_status`'s `KeyError`.
- **`artifacts(run_id, kind=None)`** — lists all artifacts for a run (optionally filtered by `kind`), returned as plain dicts with an ISO-formatted `created_at`.
- **`get_run(run_id, *, include_artifacts=False)`** — returns the run as a dict, optionally embedding the full artifact list.
- **`events_since(run_id, sequence=0)`** — polling primitive: all events with `sequence > sequence`, ordered ascending. This is how the web layer implements incremental progress polling without websockets.
- **`list_runs(limit=30)`** — fetches the most recent run rows, but only keeps their `.id`, then calls `get_run(id)` once per row (N+1 query pattern) to rebuild the dict. It never passes `include_artifacts=True`, so artifact lists are always omitted from run listings. The walrus-operator filter (`if (r := self.get_run(i))`) silently drops any run deleted between the two queries — no error, just a shorter list than `limit` implied.

## Non-obvious logic worth flagging

- `_json()` recursively converts Pydantic `BaseModel`/list/tuple/dict values before `json.dumps`, but falls back to `default=str` for anything else — so an unrecognized object type (e.g. a `datetime` nested inside a plain dict value) is silently stringified rather than raising. Dict *keys* are never converted, only values.
- The `cascade="all, delete-orphan"` relationships on `RunRow.events`/`RunRow.artifacts` are declared but unused: there is no delete method anywhere in this file, and no code path exercises cascade deletion.
- No connection pooling tuning beyond the SQLite WAL pragmas; a Postgres `database_url` gets a bare `create_engine(database_url)` with no pool-size or pragma configuration.

## Connections

`Repository` and its `RunRow`/`EventRow`/`ArtifactRow` types are imported directly by `pipeline/__init__.py` (the orchestrator that drives runs through the stages in `RunStatus`) and by `web/app.py` (the FastAPI/web layer that creates runs, polls `events_since`, and reads artifacts/reports for display). `pipeline/test_budget.py` also imports it, presumably to construct a `Repository` against a temp SQLite file for pipeline-level tests. It imports `NewsBatch` and `RunStatus` from `..models`, so any change to those types' JSON shape is visible here only insofar as `batch_json`/`payload_json` round-trip through `model_dump_json()`/`json.loads()` — this file itself does no schema validation on read.
