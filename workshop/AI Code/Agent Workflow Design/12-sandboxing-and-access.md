# 12 — Sandboxing and Access Control

[Back to macro](00-macro.md) · Status: exploration draft

## The four questions

For every agent stage, the controller must be able to answer:

1. **What can the agent see?** Which files are present and readable.
2. **Where can it write?** Which folder, which branch, which paths inside it.
3. **What can it run and reach?** Shell commands, network hosts, credentials.
4. **What did it actually change?** The exact diff, checked against what was allowed.

Earlier sections mention this but do not define a mechanism: [03](03-plans-and-queue.md) has `allowed_paths`, [05](05-roles-and-handoffs.md) says reviewers are read-only and prompts are not isolation, and [06](06-workspaces-and-integration.md) notes worktrees do not isolate processes, credentials, or network. This section defines the mechanism.

## Principle: layered controls, strongest first

A prompt saying “only edit `src/`” is a request, not a control. The strongest control is that a file is not there at all. Use the following layers together:

| Layer | Controls | Strength |
| --- | --- | --- |
| 1. Workspace construction | What exists in the agent's folder | Strong for visibility; see the `.git` caveat |
| 2. Vendor permissions and sandbox | Tool-level and OS-level read, write, network rules | Strong when configured correctly; differs by vendor |
| 3. Container or VM | Everything outside the mounted folders | Strongest; costs setup and authentication effort |
| 4. Controller diff check | What changed, after the stage | Detection only; it cannot prevent |
| 5. Credentials and network | Secrets and outbound connections | Needed in every setup |

## v1 sandbox (Oct 10)

The realistic risk is an accident, not malware: deleting the wrong folder, a force-push, editing another repository, touching `~/.ssh` or dotfiles. Agents can do whatever the plan needs inside these limits:

- **One separate clone per run** (D-44), apart from your own working folder; plans stack inside it.
- **No push credentials**; you review, merge, and push.
- **Vendor sandbox and permission rules** (layer 2), plus a **permission reviewer** (D-50) that approves truly safe actions so fewer things block at night. A denied action pauses the plan and waits for you.
- **Tests hidden** in a separate clone with a deny-read rule (D-45).
- Not in v1: the container (layer 3) and the controller's path check (layer 4); both later ([17](17-later.md) L21). The controller still commits after every node, so every change is visible in the diff.

## Layer 1 — Building the workspace

**Where code is written.** The controller prepares an isolated candidate worktree from the recorded base commit, on a branch it names, for example `run-<id>/candidate`. Sequential dependent plans may reuse that worktree with recorded checkpoints. Optional parallel writers or retry attempts use separate clean worktrees from a recorded eligible base. It launches the agent with that worktree as its working directory: the process working directory for Claude Code, and the working-directory option for Codex (verify the exact flag). The agent never chooses its own folder or branch; both are recorded in the stage state before dispatch.

> **✅ DECISION C4 — Agents get a local clone and read-only Git** (accepted Oct 9; details to work through)  
> **Problem:** a worktree keeps its index and branches in the main repository's `.git` (verified), outside the sandbox's write area. Either agents cannot commit, or, if allowed, they can move any branch, including main.  
> **Fix:** Each run gets a **`git clone --local`** of the source repository (cheap: it hard-links objects) instead of a worktree. Agents get **read-only Git**: they may run `status`, `diff`, `log`, and `show`; commands that change Git state are denied through permission rules. The **controller** makes every commit, creates branches, and fetches results back into the real repository. A mistake inside the clone cannot touch your real branches. This does not solve history visibility; snapshot isolation is still needed for truly hidden files.

**Where these settings come from (D-20):** you define visible, writable, and protected paths, network hosts, and the working folder in the [UI](16-plan-ui.md); the controller turns them into the role profiles below.

**Showing some files but not others.** Per role, the plan or specification declares `visible_paths`. Two ways to apply it:

- **Sparse checkout** of the worktree, so only the listed paths are checked out. This is cheap and keeps normal Git behavior.
- **Snapshot export**: copy only the listed paths at the base commit into a fresh directory with a new, history-free repository, then map its commits back afterwards. Use this when files must be truly hidden.

Caveat: a sparse worktree still shares the full repository history, so `git show <commit>:<hidden-file>` can reveal hidden files. Sparse checkout hides files from casual reads, not from a determined agent. Use snapshot export for real confidentiality.

Untracked local files such as `.env` are not copied into new worktrees. This is a useful default. Do not add them back unless the plan declares them.

> **✅ DECISION C3 — Per-repository runner profile, proven during the day** (accepted Oct 9; details to work through)  
> **Problem:** excluding `.env` conflicted with running checks.  
> **Fix:** Checks get placeholder environment values from the repository's runner profile, never the real `.env`; see the C3 decision in [08](08-verification-and-repair.md).

**Hiding the independent tests from Claude (D-30, mechanism D-45).** Claude's clone is created from the base commit before any test is written, and the controller only ever copies code commits into it. The tests never enter that clone's files *or* history, so this is real hiding, not the sparse-checkout kind that `git show` can defeat. The tests themselves live in a **separate clone**, not a worktree (worktrees share one `.git`, so `git log --all` or `git show tests-branch:…` would reveal them). Because Claude Code can read outside its folder by default, its settings also carry a **deny-read rule** for the tests path. The controller copies the tests into a third, check folder only, where it runs them.

**Context the agent needs but must not edit** (specification, contract, findings, receipts) goes in a separate artifacts folder that is read-only for the agent.

## Layer 2 — Vendor permissions and sandboxes

**Claude Code** (from the sandboxing docs, October 2026):

- The OS sandbox (`sandbox.enabled`) covers **shell commands only**. Writes default to the working directory, a temp directory, and added directories. **Reads default to most of the machine, including `~/.ssh` and `~/.aws/credentials`.**
- Tighten reads with `sandbox.filesystem.denyRead` and `allowRead`, for example deny `~/` and allow `.`. Alternatively, use `permissions.blockReadsOutsideWorkingDirectories`.
- Built-in Read, Edit, and Write tools run **outside** the sandbox and follow permission rules instead. You therefore need both sandbox filesystem rules and `Read(...)` and `Edit(...)` deny rules.
- Set `allowUnsandboxedCommands: false` so a blocked command cannot be retried outside the sandbox.
- Network goes through a proxy with `network.allowedDomains`, which starts empty.
- `sandbox.credentials` can deny or mask secret files and environment variables.
- The controller can pass all of this per launch with `--settings`, so each role gets its own profile.

**Codex** (from the approvals and security docs; check exact flags when implementing):

- `--sandbox read-only` for reviewers and spec drafting, `workspace-write` for writers, `--ask-for-approval never` for unattended runs.
- `workspace-write` allows writes in the working directory and temp folders. Network is off by default.
- Restricting reads outside the workspace is not clearly documented; check “permission profiles”. Until confirmed, assume Codex can read the rest of the machine, and rely on layer 3 if that matters.

### Permission reviewer (Oct 10, D-50)

Script mode cannot stop to ask you, so a reviewer decides on actions that would otherwise be refused:

- **Claude Code:** its *auto* permission mode already has a model review each action; script mode also accepts a custom approver (`--permission-prompt-tool`). Turn one of these on.
- **Codex:** check whether `codex exec` has an equivalent approval hook. If not, build a small reviewer of our own for Codex only.
- **Rules:** a cheap, fast model, because it is called on every risky action. When unsure, deny and log. A denied action pauses the plan and waits for you, with a macOS notification. Everything denied is listed in the morning summary.
- **Why it matters:** it reduces how often a run stops at night, including browser verification (Codex driving Chrome), which the sandbox may otherwise block.

**Per-path write limits inside a worktree** (for example, independent acceptance-test paths for Codex and implementation plus local-test paths for Claude) need explicit enforcement. Do not assume a working-directory sandbox enforces this division. Use applicable vendor rules, isolated writer workspaces, and the layer 4 check; verify exact capabilities before implementation.

### Proposed role profiles

| Role | Reads | Writes | Network |
| --- | --- | --- | --- |
| Spec drafter / reviewer | `visible_paths` + artifacts | none (read-only) | model API only |
| Independent test writer (Codex, before code) | `visible_paths` + artifacts | the plan's `tests/` folder, outside every implementer workspace | model API only |
| Implementer (Claude) | `visible_paths` + artifacts, **minus the independent tests and any commit containing them** (D-30) | implementation plus assigned local-test paths | model API only |
| Missing-test writer (new Claude session, after the completeness pass, D-37) | your plan, the list of existing test names (no bodies), and the repository's existing test conventions; not tonight's implementation | new test files only; existing tests read-only (prompt instruction in v1, D-47) | model API only |
| Completeness pass and test-failure fixer (Codex) | `check/` workspace: code + all tests, results, artifacts | implementation paths in `check/`; no test edits (D-37) | model API only |
| Repair round 2 (Claude, D-46) | its clone + the failure output and plan item; no hidden test source | implementation paths | model API only |
| Explain-back session (fresh Claude, morning) | final code and the functions you picked; the plan only in its second pass (D-49) | its explain-back artifacts only | model API only |
| Integrator / repairer | integration worktree | integration worktree, by finding | model API only |
| Controller verification runner | integration worktree | build outputs only | none, or a declared allowlist |

Install dependencies during preflight, then run agent stages without package-registry access unless the plan allows it.

## Layer 3 — Container or VM

Unattended overnight runs with auto-approved actions benefit from a hard boundary. Run each agent stage in a container that mounts only its worktree (read-write) and the artifacts folder (read-only), with no home directory and network limited to the model API.

Tradeoff: subscription logins are stored in the home directory or the macOS keychain, so they may not work inside a container. API keys are simpler but may be billed differently. Verify this before committing.

Proposed default: use vendor sandboxes (layer 2) for the first supervised trials. Move to a container before the first unattended overnight run on a repository you care about. **Revised Oct 10:** not in v1. Runs are on your laptop in a visible terminal, with the v1 limits above; the container comes back with a Mac mini or server ([17](17-later.md) L21).

## Layer 4 — Controller diff check (“which diff”)

After the agent exits, the controller, not the agent:

1. Records `git status --porcelain`, including untracked files.
2. Commits the agent's changes itself, so commit boundaries are reliable and the agent cannot rewrite history.
3. Computes `git diff --name-status <base>..<stage-commit>`.
4. Checks every changed path against the role's `writable_paths`.
5. Checks **protected paths** that are denied to every agent by default: `.claude/`, `AGENTS.md`, `CLAUDE.md`, hook scripts, CI configuration, test-runner configuration, lockfiles, and dependency manifests unless assigned. Editing these can widen an agent's own permissions or weaken verification.

Policy for a violation: preserve the attempt as evidence, mark the stage failed with a `scope_violation` finding, and retry once from a clean worktree with the violation fed back. Then block.

This check cannot see writes outside the worktree. Preventing those is the job of layers 2 and 3.

**v1 (Oct 10):** the controller commits after every node (D-44), so the diff is always there for you to review, but the path and protected-path checks above are not built in v1 ([17](17-later.md) L21).

## Credentials

- Start agents with a minimal environment that holds only the model credential.
- Give agents no Git push credentials. Only the controller creates branches; pushing, if ever, is a controller action.
- Never mount `~/.ssh`, cloud credentials, or browser profiles.

## Proposed plan fields

This extends the [03](03-plans-and-queue.md) format and is not executable configuration.

```yaml
access:
  visible_paths: [src/, tests/, docs/api.md]
  hidden_paths: [config/secrets/, data/customers/]
  isolation: sparse            # sparse | snapshot
  writable_paths:
    tests: [tests/acceptance/]
    impl: [src/, tests/unit/]
  protected_paths_extra: [migrations/]
  network: [model-api]         # plus any declared hosts
  container: false
```

## Evidence needed (add to section 10)

| Scenario | Expected behavior |
| --- | --- |
| Implementer edits an unassigned independent acceptance-test file | Diff check rejects it; `scope_violation` recorded |
| Agent reads `~/.ssh/id_*` | Blocked by sandbox or container; attempt logged |
| Agent edits `.claude/settings.json` or CI config | Protected-path rejection |
| Agent makes an undeclared network call | Blocked by proxy or container |
| Agent runs `git show` for a hidden file | Fails under snapshot mode; documented as a risk under sparse mode |
| Agent writes outside the worktree | Blocked by sandbox; not merely detected |
| Claude searches its clone or Git history for the independent tests (D-30) | Nothing found: no file, no commit |
| Claude tries to read the tests clone directly (D-45) | Deny-read rule blocks it |
| Agent tries to push (D-44) | Fails: no push credentials |
| Permission reviewer unsure about an action (D-50) | Denied, logged, plan pauses for you |

## Sources

Consulted on October 9, 2026; re-check exact keys and flags when implementing:

- [Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing)
- [Codex agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)

## Exploration

- Which repositories contain material that must never reach a model provider, as opposed to only being kept from edits?
- Sparse or snapshot isolation by default?
- Container from day one, or only for unattended runs?
- Subscription login or API key inside sandboxes?
- Should a scope violation retry once, or block immediately?
