# Plan 01 baseline — index

Implements `To Do/Gateway to do/GLC and ingestion gateway migration/01-baseline-and-ownership-decisions.md`.
No source was moved, no imports or ports changed, no providers/ingestion
internals refactored — all out of scope per that plan.

- `decisions.md` — the four decision checkboxes (§1-4) plus Work Package F,
  with what was chosen and why.
- `repo-state.md` — Work Package A: commit IDs, remotes, dirty-tree
  resolution, history-import policy, rollback procedure, environment/lockfile
  versions.
- `run-baselines.sh` — Work Package B: the one repeatable root-level
  baseline command. Run it with `bash migration/baseline/run-baselines.sh`
  from the repo root; each run writes a timestamped `results-*.log` next to
  it. Failures are recorded, not fixed (see the current log for what's red
  and why — mostly path/env issues in scripts invoked outside their normal
  entrypoint, not test failures).
- `contracts.md` + `contracts/glc-openapi.json` + `contracts/gateway-openapi.json`
  — Work Package C: frozen route surfaces, fixture pointers, env var
  defaults/precedence.
- `caller-inventory.md` (+ `caller-inventory-raw.txt`) — Work Package D:
  every caller of port 8111, `GLC_*`, `glc.*` imports, `glc.main`, `/v1/*`,
  `/api/ingestion/*`, classified active/doc-only/obsolete. Zero unknowns.
- `activation-state.md` — Work Package E: active-vs-dormant table for every
  domain in the program roadmap's plan sequence.

## Exit gate checklist

- [ ] All three baselines are green and recorded. **Recorded, not green** —
      see the current `results-*.log`: `glc: ruff format --check`, `glc: mypy`
      (advisory job), `glc: validate_envelope`, `glc: validate_policy`, and
      `ingestion: verify_environment` fail (mostly `ModuleNotFoundError` from
      running package scripts outside their normal entrypoint — pre-existing,
      not introduced by this capture). All GLC/ingestion/gateway/shell
      *pytest* suites pass. Fixing these is a source change, out of scope for
      Plan 01 — flagging so this checkbox isn't silently claimed done.
- [x] Current work exists in recoverable commits.
- [x] Gateway is tracked.
- [x] History policy is approved.
- [x] Contract snapshots and caller inventory are committed.
- [x] Unknown callers have an owner or an explicit compatibility requirement.
- [x] Every in-scope domain has a recorded activation state.
- [x] GLC's data-file location decision (Work Package F) is made, not assumed.
