# Dependencies (root project: core and leaves)

The gateway's are in `gateway/docs/dependencies.md`. Exact versions are in `uv.lock`.

- **pytest** (dev only) — job: runs the tests. Why: already the test runner in `gateway/` and `ingestion/`. Exit plan: the tests are plain functions and asserts, so any runner works.
