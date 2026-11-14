# Financial Tool Builder (EAG V3, Assignment 17)

Describe a financial calculation in plain English, or supply a document that contains the rules, and get a working, tested calculator as one HTML file. You agree the rules and the known answers; S17Code writes the tool; a check you cannot be argued out of decides whether it is right.

## Run it

You need `uv`, `node`, `git` and Python 3.11+. No packages are installed for this app itself: it uses only the Python standard library.

```bash
git clone https://github.com/theschoolofai/S17Code.git
git clone https://github.com/theschoolofai/glc_v5.git
(cd S17Code && git apply ../upstream/s17code-*.patch && uv sync)
(cd glc_v5 && git apply ../upstream/glc_v5-*.patch && uv sync)
cp glc_v5/.env.example glc_v5/.env      # then put your provider keys in glc_v5/.env
./run.sh                                 # starts glc_v5 (8111), S17Code (8113) and this app
```

Open http://127.0.0.1:8120. The two S17Code patches are required, not optional: without the first the engine cannot record the result of any command it runs, and without the second a run cannot be watched while it is live. Both are described under "Bugs fixed".

## How it works

**Step 1.** Describe the tool, or paste a `.txt`/`.md` document. Two examples are built in: a portfolio rebalancing calculator (from a prompt) and a fee calculator (from a fee schedule).

**Step 2.** The app shows its interpretation: inputs, outputs, each rule, and every assumption as a question. For a document, each rule shows the passage it came from, and a rule whose passage is not in the document is flagged. Nothing can be built until every rule is confirmed, every question answered, and at least one example with a known answer is confirmed.

**Step 3.** S17Code builds `index.html` in an isolated workspace. The activity panel shows the engine's own journal: planner decisions, files written, the check going red, the fix, the check going green, and any refusal. When the engine stops, the app runs the check itself and keeps the page only if that passes. You can then try the tool, download it, or ask for a change. A change arrives as proposals; agreed rules stay unless you accept their removal.

## Boundaries

The engine may edit only `workspace/`, may run only `node`, and cannot edit `checks/` or `SPEC.md`. A document's text is sent to the model fenced as data and only ever comes back as rule text for you to confirm; the engine never receives the document. The engine token stays in this app's server and provider keys stay in glc_v5; neither reaches the browser or a generated tool. Generated tools are previewed in a sandboxed frame with no network access.

## Tests

```bash
python3 -m unittest discover -s tests -t .                              # app only
uv run --project S17Code python -m unittest discover -s tests -t . -v   # plus the real engine
```

The second command starts a real S17Code server and drives it through this app. Only the model is scripted, so it runs without keys: it plays an agent that gets the fee tiers wrong (check fails), tries to rewrite the expected answers (refused), then fixes the arithmetic (check passes). A second test shows a run that never converges failing with the engine's own reason.

## Bugs fixed (patches in `upstream/`)

**S17Code 1: a command's result could not be journalled.** The worker returned a `CommandResult` object, the journal is JSON, so every command the agent ran was recorded as a failed task with no exit code. Fix: return the result's dict.

**S17Code 2: a run could not be watched live.** `POST /v1/agent/runs` answers only when the run ends and the run id was minted inside it. Fix: the caller may supply `run_id`; a reused id is refused with 409.

**glc_v5: blank text crashed the always-on speech fallback.** macOS kills `say` when given nothing to speak, surfacing as an unhandled 500. Fix: blank text returns valid silence, and a failing `say` becomes a reportable error.

Each patch contains a test that fails before the fix and passes after.

## Who wrote what

Aryaman wrote the product plan (`PLAN.md`): the two routes, the boundaries and what "done" means. Claude (an AI coding agent) wrote all the code, tests, prompts, the skill file, this README, and found and fixed the three bugs. The example fee schedule and the known answers in `examples/` are placeholders written by Claude and must be replaced by real ones.

## Not yet done

No run has used a real model yet: glc_v5 had no keys on the build machine, so interpretation and generation by a live model are unverified. The page was checked in a browser only up to the interpret step; the rest was exercised over HTTP. PDF and Word documents are not supported.

## Demo outline

Load the fee example, show a rule with its highlighted source passage, answer a question, confirm the examples, build, and narrate the activity panel. Then ask for a change and show the proposals. For the failure, stop S17Code and press Build (explicit "not reachable" error), or confirm an example with a deliberately wrong expected number so the run stops without converging.
