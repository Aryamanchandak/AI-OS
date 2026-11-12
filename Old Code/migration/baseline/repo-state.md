# Repository state — Plan 01 baseline capture

Captured 2026-09-14. This is the recoverable snapshot Plan 01 requires before
any structural import happens. Nothing in the working code changed as part of
this capture — only git history (new commits recording pre-existing dirty
work) and `.gitignore` scoping changed.

## Commit IDs at capture time

| Repo | Branch | HEAD | Remote | Ahead of origin |
|---|---|---|---|---|
| AI OS (parent) | main | `9fc863bba9a262fd30779e2cade35e52395d648e` | `git@github.com:Aryamanchandak/AI-OS.git` | 1 commit |
| glc_v5 (submodule) | main | `604e4251a407a5fbab6338ae4de6a0590da6e866` | `git@github.com:Aryamanchandak/glc_v5.git` | 2 commits |
| ingestion-pipeline (submodule) | main | `09d982ef40fc7d141c4a16ef19b2c8d66728fe93` | `git@github.com:Aryamanchandak/AI-OS-Ingestion-Pipeline.git` | 6 commits |

None of these have been pushed. All three are local-only commits sitting on
top of each repo's own `origin/main`. Pushing was out of scope for this
capture — do it deliberately, separately, when ready.

## What was dirty, and what happened to it

**glc_v5** had one commit already ahead of origin (`34dcc70`), plus a staged
rename (`HANDOFF.md` → `docs/HANDOFF.md`) and ~65 unstaged modified/deleted
files — net -825 lines (206 insertions, 1031 deletions), consistent with an
in-progress cleanup pass across channel adapters, voice providers, docs, and
two `scripts/` deletions (`check_pr_boundaries.py`, `scorecard.py`) plus
`.github/CODEOWNERS`. Diffed for secrets before committing — none found.
Committed as `604e425` ("baseline: capture in-progress working tree before
AI OS migration").

**ingestion-pipeline** had 5 commits already ahead of origin (the GLC v5
client-integration series: `d6f020c` … `e16152c`), plus staged doc renames
and 4 new untracked planning docs (`INGESTION_ARCHITECTURE_REFACTOR.md`,
`docs/GLC_V5_PROFILE_INTEGRATION_PLAN.md`,
`docs/INGESTION_PIPELINE_ASSESSMENT.md`,
`docs/WORKFLOW_ingestion_glc_v5.md`). No code changes, no secrets. Committed
as `09d982e` (same message).

**Parent (AI OS)** had `gateway/` fully untracked and no root `.gitignore`
coverage for it. Now tracked (see "Untracked root directories" below).
Submodule pointers updated to the two commits above. Committed as `9fc863b`.

## Untracked root directories — decision and rationale

Decision (confirmed 2026-09-14): **track `gateway/`** per this plan's exit
gate ("Gateway is tracked"). Everything else was evaluated individually:

- `Database/` — 517MB. Contains `Database/Raw Data/`, which is **its own git
  repository** with a remote pointing at a *different, unrelated* personal
  project (`git@github.com:aryamanchandak/Agentic-Calendar.git`) — not part
  of this migration. Also contains photos, financial documents, and personal
  notes. **Gitignored** — not something to fold into the AI OS parent repo
  without a separate, explicit decision.
- `AI Agent/` — 654MB. **Its own separate git repository** (no remote
  configured), with its own in-flight migration plan
  (`To Do/AI Agent to do/01-agent-under-gateway-plan.md`). **Gitignored** —
  out of scope for the GLC/ingestion migration this plan folder covers.
- `shell/` — the React/Vite UI shell, 208MB mostly `node_modules/`.
  **Gitignored.** Not mentioned anywhere in Plan 01; tracking it is a call
  for whoever owns `To Do/UNIFIED UI/UNIFIED_UI_PLAN.md` to make.
- `Project plan/`, `To Do/` — lightweight docs/plans (288K + 168K, no nested
  repos, no data, no secrets). **Tracked.** This was revised mid-capture:
  `To Do/Gateway to do/GLC and ingestion gateway migration/01-baseline-and-ownership-decisions.md`
  itself — the plan's own decision checkboxes — lives in this tree. Leaving
  it gitignored would have made the approvals recorded in `decisions.md`
  unrecoverable from git and every later plan in that folder untracked too.

Also added to `.gitignore`: `__pycache__/`, `*.pyc`, `.pytest_cache/`,
`.mypy_cache/`, `node_modules/`, `dist/` — none of these existed as ignore
rules before, and `gateway/` and `shell/` both generate them.

No `.env`, credential, key, or token files were found in `gateway/`,
`Database/`, or `AI Agent/` at the depth searched (`Original Code/` — already
gitignored — has three `.env` files under old course/project snapshots; left
untouched).

## History import policy (Plan 01 §1)

**Decided: preserve full history.** When GLC and ingestion are later
structurally imported into the gateway (Plan 06 and the GLC plans), use a
history-aware import (e.g. `git subtree add` or `git filter-repo` against a
copy) so every commit on `main` in both `glc_v5` and `ingestion-pipeline`
carries into the parent repo, then move paths in separate follow-up commits.
Do not squash to a single snapshot commit.

## Rollback procedure

Every step above is reversible without loss:

- Parent repo: `git reset --soft 2961eef` un-commits the two baseline
  commits above (`9fc863b`, and its predecessor before that if needed) while
  keeping the working tree; `git revert` is the safer option if the commits
  are already shared. Submodule pointers can be moved back with `git
  checkout 2961eef -- glc_v5 ingestion-pipeline` followed by `git submodule
  update`.
- glc_v5 / ingestion-pipeline: each baseline commit is a normal local commit
  on `main`, not pushed. `git reset --soft HEAD^` inside either submodule
  undoes it while keeping the tree dirty again exactly as found. Nothing was
  force-pushed or rewritten.
- No destructive git operations (`reset --hard`, `push --force`, history
  rewrites) were used anywhere in this capture.

## Environment

- Python: `3.11` required by both `glc_v5/pyproject.toml` and
  `ingestion-pipeline/merged-ingestion/pyproject.toml` (`requires-python =
  ">=3.11"`); both have `uv.lock` and their own `.venv`, managed by `uv`.
  System default is `3.9.6`; `uv run` resolves 3.11 correctly regardless.
- `gateway/` has no `pyproject.toml`/lockfile of its own — its README
  documents running it with `ingestion-pipeline/merged-ingestion/.venv/bin/python`.
  This is a real gap (no independent dependency pin for gateway/), noted for
  Plan 02 ("Gateway foundation"), not fixed here.
- Node: `v25.8.2` / npm `11.11.1`; `shell/` has `package-lock.json` and its
  own `node_modules/` (208MB, gitignored).
