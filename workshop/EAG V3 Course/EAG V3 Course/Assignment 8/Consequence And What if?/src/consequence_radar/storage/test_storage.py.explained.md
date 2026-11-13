# `storage/test_storage.py` explained

Two tests for `Repository`, both exercising a real on-disk SQLite file under `tmp_path` (no mocking of the DB layer).

## `test_complete_handbuilt_run_roundtrips_without_loss(tmp_path, graph)`

Uses the `graph` fixture from the root `conftest.py` — a small hand-built `CausalGraph` with 3 nodes, 2 edges, 1 assumption, and one `Estimate` (`Q1`) whose `estimate_type` is `"directional_only"` and which has no numeric `central` value set (that field isn't passed to the `Estimate(...)` constructor in the fixture, so it takes its model default, presumably `None`).

The test builds a full run end to end through the `Repository` API rather than touching the database directly:

1. Creates a repo against a fresh file (`Repository(...); repo.init_schema()`), creates a run from a minimal `NewsBatch`.
2. Saves the `graph` fixture as artifact kind `"graph"` version 1, then saves a modified copy (`version=2`) with `version` bumped on the model itself.
3. Saves a `"claims"` artifact (a raw list of dicts, not a Pydantic model) and a `"report"` artifact (a full `NewsletterReport`).
4. Asserts `repo.artifact(run_id, "graph")["version"] == 2` — confirms that omitting `version` in `Repository.artifact()` really does return the latest one, not just the first inserted.
5. Asserts `repo.artifact(run_id, "graph", version=1)["estimates"][0]["central"] is None` — this is the load-bearing assertion. It confirms two things at once: that requesting an explicit older version returns that exact version (not the latest), and that an estimate with no numeric value round-trips through `model_dump_json()` → SQLite text → `json.loads()` as JSON `null`, not as a dropped/omitted key or a coerced value like `0`. In other words, "no estimate yet" is preserved as an explicit null rather than being silently lost or misrepresented as zero — which matters because a `0` would look like a real (and very different) quantified estimate.
6. Asserts `repo.get_run(run_id)["batch"]["items"][0]["url"]` round-trips correctly — the input `NewsBatch` survives its serialize/store/reload cycle.
7. Asserts `len(repo.events_since(run_id)) == 1` — only the single `"queued"` event that `create_run` implicitly writes exists; none of the artifact saves in this test add events (artifact writes and event writes are independent in this repository, confirming they're not implicitly linked).

Together this test is really a persistence-fidelity check for `Repository`: multiple artifact kinds, multiple versions of the same kind, and a batch with nested Pydantic models all have to survive the JSON round trip losslessly, including preserving `None` as `None`.

## `test_path_with_question_mark_roundtrips(tmp_path)`

Builds a database path containing a literal `?` in a directory name (`tmp_path / "dir?name" / "db.sqlite"`) and confirms `init_schema()` and `create_run()` both work against it. This is the direct regression test for the `sqlite:///` branch in `Repository.__init__` that uses a custom DB-API `creator` instead of letting SQLAlchemy parse the URL — without that workaround, SQLAlchemy would parse the `?` as the start of a URL query string and either mis-locate the database file or raise. It matters concretely for this project because the project root itself is `.../Consequence And What if?`, i.e. every default `database_url` in `config/__init__.py` contains a `?`.

## Connections

Imports `Repository` from `consequence_radar.storage` and `NewsBatch`, `NewsItem`, `NewsletterReport` from `consequence_radar.models`. Relies on the `graph` fixture defined in the project-root `conftest.py`.
