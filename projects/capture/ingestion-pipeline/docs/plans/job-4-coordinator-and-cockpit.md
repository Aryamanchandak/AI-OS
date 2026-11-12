# Job 4: shrink the coordinator and decide the cockpit

Date: 2026-11-12. Status: outline only, nothing implemented. Detailed when job 3 is done.

## What

The coordinator is the code that walks one run through its stages and stops at each point where you have to decide something. It is 2,862 lines across eight files, and `coordinator.py` alone is 1,375, close to your 1,500-line limit. The cockpit (`cockpit/server.py`, 767 lines) is the web API for those decisions. It has no screen and no app that mounts it.

## What changes once Graphiti is in

The `PROPOSAL_REVIEW` stage has nothing left to review, so it and its gate code go. In `coordinator.py` that is 58 places that mention proposals. The stages that stay are the ones that encode your judgment before anything reaches the graph: intake checks, the abbreviation and spelling review, book identification and the Obsidian capture.

## Steps, one commit each

Step 1 removes the proposal-review stage and its gates, with the matching tests in `test_coordinator.py` (1,680 lines today) listed for your approval.

Step 2 splits what is left of `coordinator.py` only if it is still doing more than one job after step 1. I will measure first and tell you, not split on principle.

Step 3 acts on your cockpit decision below.

## Done when

A real run with one book photo and one note reaches "complete" with every remaining human decision still asked. `coordinator.py` is under 1,000 lines. All remaining tests pass.

## Needs your answer before starting

Where does human review sit now? With Graphiti the only place left is before the graph: you approve the passage text, and Graphiti does the rest. If you agree, the intake and cleanup gates are that review and nothing new is needed.

What happens to the cockpit? Three choices. Keep the API and build a phone-first screen for it inside the AI OS shell. Keep the API as it is until the shell is ready. Or delete it and run the gates from the command line for now. I'd keep it untouched until the shell exists, since the gates it serves are staying.

## Depends on

Job 3. This job should not start before the old proposal code is gone, or it gets done twice.

## Not in this job

What starts a run (a folder watcher or a schedule), and any change to the intake gates themselves.
