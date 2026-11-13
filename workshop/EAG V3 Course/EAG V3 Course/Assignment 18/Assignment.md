The assignment
Total: 2000 points. Build an evaluation around one small coding-agent capability.

Part 1: make an evaluable task set (900 points)
Create three tasks for a fork of S18Code or another, runnable coding harness (QwenCode, OpenCode, etc). For each task, submit:

the behaviour being evaluated in one sentence;
its reachability contract: files, data, network, protected paths, and allowed tools;
acceptance checks and one reason they are not the whole specification;
the task type: source repair, integrity boundary, or unavailable dependency; and
one attack or counterexample you ran against the task design.
Describe in your Github README.md and submit that link.

Part 2: run and record (800 points)
Run one fixed agent configuration three times on each task (3 different harness). Save a raw JSON journal per run before scoring it. Write a scorer that produces the four fields from Section 4.

Show one scoring change and rescore the existing journals without calling the model again.

Submit: Github link for Test Results, README, JSON, etc.

Part 3: make one narrow claim (300 points)
Write a one-page report that begins:

Under this manifest, we observed...

Include the raw counts, the failures, the cost, and one thing the evaluation still does not establish. Do not write a leaderboard sentence.

Submit: Separate Github Report