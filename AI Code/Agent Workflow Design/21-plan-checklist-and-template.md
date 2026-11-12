# 21 — Plan Checklist and Template

[Back to planning overview](20-planning-workflow-macro.md) · [Back to macro](00-macro.md) · Status: exploration draft for your comments · Created Oct 10

## Purpose

This is the list of **everything a plan needs to be complete**, so the agents never have to assume anything. Use it two ways:

- **As a template:** copy the block at the bottom and fill it in.
- **As the audit checklist:** the audit prompt ([23](23-agent-prompts.md), P1) checks your plan against every field below.

**Required** fields must be filled in. **If applicable** fields are either filled in or marked “n/a, because …”. A blank field is a gap.

**Left out on purpose:**

| Item | Why it's left out |
| --- | --- |
| Stable plan IDs | The plan's folder name identifies it |
| Per-item IDs | Optional in v1 (D-48) |
| Repository path | You give the folder |
| Starting branch | It's the code that already exists |
| Commit policy | The same for every plan |

## The checklist

| # | Section | Required? | What it must say | What the agent would otherwise guess |
| --- | --- | --- | --- | --- |
| 1 | **Title and one-line goal** | Required | What this plan achieves, in one sentence | — |
| 2 | **Work mode** | Required | Refactor, rewrite, or large feature ([15](15-work-modes.md)) | Which tests matter: keep vs change |
| 3 | **Problem and background** | Required | Why this is being done; what's wrong or missing today; relevant history | The motivation, and therefore trade-offs |
| 4 | **Desired behaviour** | Required | What the user or caller sees when it's done, with concrete examples (input → output), including negative cases | What “done” means |
| 5 | **How you want it built** | Required | Structure, modules, files to create or change, patterns to follow or avoid, libraries allowed or banned | Architecture — the biggest source of surprises |
| 6 | **Interfaces and data shapes** | Required | Function or class signatures, endpoints, CLI flags, file formats, schemas, types; names exactly as they should appear | Names, signatures, shapes |
| 7 | **Behaviour changes: keep / change / remove** | Required | Three short lists: behaviour that must survive; behaviour that changes (old → new); behaviour deliberately deleted, plus what happens to its old code and tests | Whether old behaviour may break, and what to do with old code |
| 8 | **Error behaviour** | Required | What happens on each failure: message, exit code or exception, retry or not, what is logged | Silent failures, swallowed errors |
| 9 | **Edge cases: every dimension answered** | Required | For each feature, each dimension below is either “applies: case → expected behaviour” or “n/a, because …” | Every edge case |
| 10 | **Scope and non-goals** | Required | What's in, what's explicitly out, what must not be touched | Scope creep and “helpful” extra changes |
| 11 | **End-to-end scenarios** | Required | For each feature: a command, real input, expected output, run from entry point to final output (D-34) | What “works top to bottom” means |
| 12 | **How to run and verify** | Required | Setup steps, the test command, build, type check and lint commands, and how to run each scenario | How to prove it works |
| 13 | **Output contract** | Required | Where the change receipt goes and what it must contain beyond the default; any other documents to produce | What to hand back |
| 14 | **Provides to later plans** | If applicable | Files, interfaces, data shapes and behaviour later plans will build on, stated exactly | What later plans can rely on |
| 15 | **Assumes from earlier plans** | If applicable | Which earlier plan(s), and exactly which of their declared outputs this plan uses | Whether a dependency exists, and its shape |
| 16 | **Migration** | If applicable | Only if stored data or config formats change: old format, new format, how existing data is converted, whether it can be rolled back | Data loss |
| 17 | **Constraints** | If applicable | Performance limits, compatibility (versions, platforms), security, things to preserve exactly | Defaults that may not suit you |
| 18 | **Attachments and context** | If applicable | Specs, examples, reference code, screenshots, sample data, and what each is for | Missing context |
| 19 | **Run settings** | Required | Run window (D-41), sandbox (writable, visible and protected paths, network), working folder | Set in the UI ([16](16-plan-ui.md)) |
| 20 | **Open questions** | Required: must be empty to queue | Anything you haven't decided yet | — |

### Edge-case dimensions (for row 9)

For each feature, answer every one of these:

1. Empty, missing, or invalid input
2. Duplicate actions and retries
3. Interruption and partial completion
4. Concurrent activity
5. Large inputs and resource limits
6. Permissions and access
7. Schema or format compatibility (old data, old callers)
8. External-system failure (network, files, services)
9. Downstream assumptions (what callers rely on)

Each answer is either **“applies: case → expected behaviour”** or **“n/a, because …”**. Every “applies” answer becomes a test or an end-to-end scenario.

## Template

Copy this into `plan.md` and fill it in.

```markdown
# <Title>

**Goal:** <one sentence>
**Work mode:** refactor | rewrite | large feature

## 1. Problem and background
<why, what's wrong or missing today, relevant history>

## 2. Desired behaviour
<what the user/caller sees when done>

Examples:
- <input> → <output>
- <invalid input> → <error behaviour>

## 3. How it should be built
- Structure / modules: <...>
- Files to create: <path — purpose>
- Files to change: <path — what changes>
- Follow: <patterns, existing code to imitate>
- Avoid: <patterns, libraries, approaches>

## 4. Interfaces and data shapes
<signatures, endpoints, flags, schemas, file formats — exact names>

## 5. Behaviour changes
**Keep (must still work exactly as today):**
- <behaviour>

**Change (old → new):**
- <old behaviour> → <new behaviour>

**Remove (deliberately deleted):**
- <behaviour> — old code: <delete / leave>; old tests: <delete / rewrite>

## 6. Error behaviour
| Failure | What happens (message, exit code / exception, retry, logging) |
| --- | --- |
| <failure> | <behaviour> |

## 7. Edge cases
### <Feature name>
| Dimension | Answer |
| --- | --- |
| Empty / missing / invalid input | applies: <case> → <expected> / n/a, because <...> |
| Duplicates and retries | |
| Interruption / partial completion | |
| Concurrent activity | |
| Large inputs / resource limits | |
| Permissions / access | |
| Schema / format compatibility | |
| External-system failure | |
| Downstream assumptions | |

## 8. Scope
- In: <...>
- Out (do not do): <...>
- Do not touch: <paths, modules>

## 9. End-to-end scenarios
| Scenario | Command | Input | Expected output |
| --- | --- | --- | --- |
| <name> | <command> | <input> | <output> |

## 10. How to run and verify
- Setup: <commands>
- Tests: <command>
- Build / type check / lint: <commands>

## 11. Output contract
- Change receipt: `docs/plans/<plan-folder>/receipt.md` (default contents: what was written where, interpretations first, tests added, disputes, out-of-scope suggestions, what couldn't be verified)
- Also produce: <any other documents, or "nothing else">

## 12. Provides to later plans  (if applicable, else "n/a")
- <file / interface / data shape — exact>

## 13. Assumes from earlier plans  (if applicable, else "n/a")
- From <plan folder>: <declared output used>

## 14. Migration  (only if stored data or config formats change, else "n/a")
- Old format → new format; conversion; rollback

## 15. Constraints  (if applicable, else "n/a")
- <performance, compatibility, security, must-preserve>

## 16. Attachments
- <file> — <what it is for>

## 17. Open questions  (must be empty before queueing)
- <none>
```

Run settings (run window, sandbox, working folder) are set in the UI, not in this file.

## Exploration

- Is anything missing from the list for the kind of work you do?
- Is anything here more than you'd actually write? Which rows would you merge or drop?
- Should the edge-case table be per feature (as above) or one table for the whole plan?
- Should “How to run and verify” live in each plan, or once per repository with plans only adding to it?
