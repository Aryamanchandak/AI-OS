# Assignment code review — 13 Nov 2026

Covers the four assignments that have code commits beyond the starting commit: 8, 9, 10 and 13. Assignments 4–7 and 14–18 have no new code commits (14 only has course code pulled in, not yet committed).

How I checked: read every changed file in each assignment's own commit history, ran each test suite, ran the key-free demo runs, and wrote small throwaway scripts to try awkward inputs. Nothing in any assignment folder was changed.

Overall verdict: the offline behaviour of all four is signed off — tests pass and the code does what its README says. None of the four is signed off as a finished submission, because no assignment has yet been run against a real model, website or desktop. Each README says this honestly.

Update, same day: seven of the problems below are now fixed, each with a new test written first. They are marked **Fixed**. The fixes are in the working folders and are not committed yet. Test counts below are after the fixes.

## Assignment 8 — comparison agent on a step graph

Commits `1f2770a`, `6fb6480`. Tests: 114 passed (`./compare test -q` inside `DAG Agent/`).

What was built. `DAG Agent/` is the active agent; the three older projects were moved, unchanged, into `Previous Implementations/`. The new feature compares 2–12 options on shared criteria. The Planner (`agent/planner.py`, `comparison_plan`) builds one evidence-reading branch per option, then an align step, an optional chart, and a report step. `agent/comparison.py` is the rule engine: every value must quote a passage that really exists in its source, numbers must appear in the quote, units convert only through `units.yaml`, and no winner is declared when dates, scopes or evidence are missing. `agent/executor.py` gained three generic things: tools can receive upstream outputs (`context: true`), runs save checkpoints and can pause and resume (`agent/state.py`), and generated Python needs a typed "yes" before it runs. `agent/llm.py` calls Claude directly; `agent/sources.py` reads files and public web pages and refuses private network addresses.

What to look at when you review. Run `./compare --request examples/service-plans.yaml --prioritise cost` and check the answer against the YAML by eye: Plan A's 100 per month becomes 1,200 per year, Plan C wins on cost, and "Support" claims no winner because Plan C has none. I ran this and got exactly that.

Problems found.

1. **Fixed.** Live mode broke if the model wraps its answer in a code fence. `agent/comparison_tools.py:18` parses each upstream output as strict JSON, while the framing and interpretation steps tolerate surrounding text. A fenced reply stopped the whole run. `align` now reads the JSON object inside the fence; a reply with no JSON at all still stops the run.
2. **Fixed.** Critic recovery assumed the last node the Planner lists is the final one (`agent/executor.py:260`). It now finds the one repair node nothing else feeds, and fails the run if there is not exactly one. This is a new rule: a repair that ends in two parallel nodes is now rejected.
3. A quote like "50-100 per month" is read as minus 100, so a correct value of 100 is rejected (`agent/comparison.py:104`). It fails safe, but it will reject real price ranges.
4. Two code-running steps in the same parallel layer each report the other's output files as their own (`agent/sandbox.py:50` and `:72`).
5. Small: when one option simply has no evidence, the warning says "dates differ or are missing", which misdescribes it. When every option fails a hard limit, the ranking silently disappears.

Against the brief. Still missing: the five base queries run live with timings, a live Critic pass-and-fail (today it is only shown with scripted replies via `--mock`), and the video. Two things a reviewer may question: the Executor was modified (the brief calls that "reportable" — the README reports the context mechanism but not checkpoints or code approval), and the comparison graph is written by code, not emitted by the model.

## Assignment 9 — browser comparison agent

Commits `e046c6b`, `0c387e2`, `44c47d9`. Tests: 68 passed, including one that drives a real Chromium browser over three made-up shop pages.

What was built. The task is a running-shoe comparison for a fixed profile (`S9/code/examples/beginner_runner.yaml`). `browser/driver.py` now saves the text of every page it visits, so evidence from product A survives moving to product B. `browser/skill.py` treats HTTP 401, 403 and 429 as "blocked" even with no CAPTCHA text. `skills.py` stopped cutting the prompt at 20,000 characters (it was silently dropping the third retailer) and now shows the Critic the original page evidence alongside the table it is judging. `dry_run_shoes.py` runs the whole pipeline with scripted model replies and no keys; its `evaluate` function holds the eligibility rules (budget, size, stock, delivery), with unknown facts never counted as a match.

What to look at. Run `uv run python dry_run_shoes.py` in `S9/code/` and open the report it prints. Expect 3 qualifying shoes and 3 excluded (over budget, wrong size, sold out), all labelled fictional.

Problems found.

1. **Fixed** (README line corrected). Line 18 marked `skills.py` as `[UNMODIFIED]`, but the file has two changes, one of which special-cases the Critic by name (`S9/code/skills.py:269`). `flow.py` really is untouched. Since the brief says the orchestrator must not be modified, the README should state this accurately.
2. **Fixed.** With the 20,000-character cap gone, prompt size had no ceiling (`S9/code/skills.py:180`). Each visited page adds up to 6,000 characters, and a page that changes slightly each turn (a countdown, a carousel) is saved again every turn. Each browser step now passes on at most 60,000 characters (about ten pages), keeping the most recent pages whole and stating how many earlier ones were left out. The 60,000 figure is my choice — change `MAX_EVIDENCE_CHARS` in `browser/driver.py` if you want a different limit.
3. If reading the page text times out (`S9/code/browser/driver.py:230`), the error is not caught inside the step, so that browser attempt ends instead of counting as one failed turn.
4. If the first browsing method fails and the fallback also fails, the page text already collected is thrown away.

Against the brief. No real retailer comparison has been run, so there is no real replay, table or cost summary yet. The dry run is integration proof only.

## Assignment 10 — macOS computer-use skill

Commits `3d86ca8`, `f01b16c`, `800a74a`. Tests: 68 passed. `python -m computer.run --dry-run` prints the plan; `python -m computer.evidence` correctly prints PENDING because no live run exists.

What was built. All desktop control now goes through one file, `code/computer/backend.py`, which calls the pinned cua-driver program (downloaded and checksum-verified by `scripts/prepare_driver.py`). `code/computer/skill.py` tries the cheapest method first: read the screen, then supplied keystrokes, then the Electron page route, then a text model over the accessibility tree, then vision. A model saying "done" is never trusted on its own; `_verify` checks the real window state. `code/computer/recorder.py` treats any recording failure as a failed run. The three tasks are in `code/computer/tasks.yaml`: Calculator 47 × 13 = 611 by keystrokes, read the active editor tab through the Electron route, and click the orange square by vision. `code/computer/evidence.py` is a read-only checker for the finished recordings. A copy of the V9 gateway lives in `llm_gatewayV9/`.

What to look at. `tasks.yaml` (the three goals and their expected results) and `evidence.py` (what counts as proof) are the two files that encode your rules.

Problems found.

1. **Fixed** (the rerun failure; apps are still left open). Nothing closes the apps a run launches. After one editor run, the debugging port stays in use, so the next editor run is refused with "port already occupied" (`code/computer/run.py:60`). The README tells you to run each task singly and then all three together, so the second editor run would fail. The editor setup now moves to the next unused port (up to ten) and still never attaches to a port something else holds. Each run also leaves a throwaway browser or editor profile folder in `code/state/`.
2. **Fixed.** Running a single task overwrote `summary.json` with only that task, and the evidence check then failed. A single-task rerun now replaces only its own row.
3. If a run is killed part-way, the driver's recording stays switched on and every later run refuses to start (`code/computer/recorder.py:47`). There is no documented reset command.
4. `code/flow.py:289` — the orchestrator — has a one-line change to pass an error code through. Small, but the skill is meant to drop in without orchestrator changes, so it should be mentioned in the README.
5. Small: a failed run's record says it was resolved at layer "extract" (`code/computer/skill.py:441`); the read-only shortcut at `skill.py:230` makes the Electron exception four lines above it pointless; the `*` key mapping assumes a US keyboard layout.

Not checkable offline: whether click positions from the screenshot land in the right place on a high-resolution display, and anything involving permissions.

Against the brief. All three live runs, their recordings and the video are still to do.

## Assignment 13 — research advisor

Commits `2d926fa`, `594c615`. Tests: 72 passed in `S13Code-2`, 13 passed in `S13Proof`, lint clean.

What was built. `S13Code-2/s13code/advisor.py` adds `POST /v1/agent/advisor`. A worker sends a question, a draft and up to four claims. The advisor fetches current documents in the caller's scope, asks the model to mark each claim supported, contradicted or unclear, allows one follow-up search, and then code — not the model — turns the verdicts into accept, revise or insufficient evidence. Every citation must be an exact quote from a fetched document and is re-checked twice in case the document changed mid-review. `S13Proof/s13proof/advisor_proof.py` replays this over real HTTP with scripted replies, `advisor_evaluation.py` compares retrieval against a fixed 40-word baseline, and `advisor_comparison.py` is a with-and-without-advice runner. The change to `runtime.py` fixes a missing bracket in the course code.

What to look at. I re-ran both proofs and the numbers match the README: recommendation "revise", one follow-up used, the stale-document attack returns "failed", and the full passage is found for 10 of 10 questions against 4 of 10 for the baseline. The 13 labels in `sandbox/advisor_judgment_cases.csv` are marked as drafts needing your review — that is a "what correct looks like" call only you can make.

Problems found.

1. **Fixed.** The validation was strict enough that a real model would often fail it, and one failure fails the whole consultation with a generic message. I confirmed three cases: a quote that crosses a line break with the break written as a space (`advisor.py:99`), a reply wrapped in a code fence (`advisor.py:176`), and an "unclear" verdict that leaves out the empty citations list (`advisor.py:37`). All three are now accepted. A quote must still be the same words in the same order as the source; only spacing may differ, and the stored quote is always the source's own text. Invented quotes, invented records and non-JSON replies still fail. The failure message is still generic.
2. A true quote can back a false claim. I had it accept "Costs were 900 units" by quoting the words "Costs were" from a document saying 100. The README admits this limit; it is the main thing the live comparison needs to measure.
3. The brief asks to show the attack failing before the fix. Test and fix are in the same commit, so the "before" exists only as a sentence in the README.
4. One stored document with no source recorded makes every retrieval fail (`advisor.py:82`).

Against the brief. Still to do: open the pull request against S13Code, and run the live comparison. The caller-supplied scope is not authenticated, which is inherited from the course code and stated in the README.

## State of the repos

Assignments 10 and 13 are pushed. Assignment 8 has 1 commit not yet pushed and Assignment 9 has 3. In the AI OS repo all four sets of changes are still uncommitted.
