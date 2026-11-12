# 03 — Plans and Queue

[Back to macro](00-macro.md) · Status: exploration draft

## Intake (revised Oct 9)

Plans enter through the [UI](16-plan-ui.md) as your detailed English plan plus attached files, sandbox, and working folder (D-20). The local backlog is parked. Agents harden the plan during the day before it can be queued; see [14](14-plan-refinement-and-local-backlog.md).

## Plan intake

Keep the original plan immutable for a run. Save its content hash and derive the implementation specification separately. Editing a plan later should create a new revision rather than altering the meaning of an active run.

A useful plan contains (most fields are set in the UI; see [16](16-plan-ui.md)):

- Stable ID, title, repository, and starting branch or commit policy. [what does a stable id tell you ? the title sure, the repositroy will be given or rather the folder will be given you dont need to worry about getting it, assume you WILL BE GIVEN IT, STARTING BRANCH IS THE CODE THAT ALREADY EXISTS, ADN COMMIT POLICY IS THE SAME FOR EVERYONE] 
- Problem, desired behavior, and relevant background. [YES BUT THE PLAN MODE, WILL NEED TO BE IN MUCH MORE DETAIL HERE, WHERE WE CLOSE ALL THE DIFFERENT LOOP HOLES THERE ARE, AND ARTICULATE EVERYTHING WE WANT TO ARTICULATE SO THE AI AGENT DOESNT NEED TO ASSUME ANYTHING] 
- Acceptance criteria with IDs. Every plan item (criterion, keep/change/remove behavior, migration step) gets an ID that tests map to, so the coverage ledger can decide completeness (D-33). *v1: IDs optional; the ledger is parked (D-48). [IS THIS NOT UNECCESSARILY COMPLICATED ?? THE MIGRATION STEP ? KEEP CHANGE REMOVE BEHAVRIOUR FOR THE PLAN WILL OF COURS EBE METNIONED IN THE PLAN, BUT MAKE A LIST OF EVERYTHIGN A PLAN NEEDS FOR COMPLETENESS SO I CAN ADD THAT TO THE PLAN WORKFLOW SO WE DONT MISS NAYTHING, ALSO AS REQUESTED IN PLAN 2 WHERE IS THE PLAN FOR THE PLAN WORKFLOW ?? RIGHT NOW I ONLY SEE PLANS FOR THE IMPLEMENTATION WORKFLOW]* 
- Constraints, excluded changes, and allowed assumptions. [ WILL BE INCLUDED IN THE PLAN] 
- Work mode: refactor, rewrite, or large feature (bug fix parked). P[WHAT DO YOU MEAN BY BUG FIX PARKED ?]
- Dependencies on other plans, each requiring automated verification or human acceptance. *v1 (D-44): all queued plans run one after another; plan N+1 starts only once plan N is confirmed done, on top of its commits. [OF COURSE]*
- Behavior preserved or changed, affected callers, migration needs, and manual acceptance evidence. [IF REQUIRED THEN ADD TO THE LIST, AFFECTED CALLERS, AND MIGRATION NEEDS ? ISNT THAT THE WHOLE POINT OF THE PLAN ? AND MANUAL ACCEPTANCE EVIDENCE WHAT IS THAT FOR ?] 
- Known verification commands and any setup requirements. [WHAT IS THIS ?]
- End-to-end scenarios: real inputs, run from the entry point to the final output (D-34). [YES BUT THESE ARE PLANS, THEY MAKE SMALLED PARTS OF THE CODE, HOW WILL YOU HAVE AN INPUT WHERE LIKELY THAT THE INPUT ACCEPTING SECTION MAUYBE I CAN DESCRIBE WAHT THE PART OF THIS CODE SHOULD DO WHAT INPUT IT NEEDS TO ACCEPT AND YOU CAN TEST ACCORDINGLY] 
- Priority and run window (set per plan in the UI, D-41). Fixed in v1: repair limit 2 rounds (D-46), node timeout 2 hours (D-52), weekly usage stop at 95% (D-43).



## Example intake structure

This is a proposed format, not executable configuration.

```yaml
id: plan-001
revision: 1
title: Add export support
repository: /path/to/project
mode: feature
depends_on: []  # nonempty entries identify plan ID and automated_verified / human_accepted gate
human_acceptance: pending
acceptance_criteria:
  - id: AC-01
    description: Export preserves the displayed column order.
allowed_paths: [src/, tests/]
verification:
  - command: project-specific-test-command
repair_limit: 3
```

Narrative details can remain in a Markdown plan referenced by the queue. Avoid forcing complex product reasoning into configuration fields. [IS THIS THE PLAN OF WHAT NEEDS TO BE BUILT OR WHAT WE ARE GIVING THE AI AS A META DATA SCHEMA ?] 

## Readiness and selection

A plan is eligible when its declared dependency gates are satisfied [DEPENDENCY GATE IS THE PREVIOUS PLAN OR EXPECTED CODE THAT IS NEEDED, THAT WILL BE THERE I WILL TELL YOU WHICH PLAN TO EXECUTE FIRST AND THEN WHICH PLAN TO EXECUTE AND THE ORDER OF EXECUTION], the repository is available [WILL BE YOU DONT NEED TO CHECK FOR THIS] , required inputs exist [ASSUME THEY WILL FOR NOW], and remaining run limits permit dispatch. Resolve known product blockers during refinement when possible; revalidate repository state, baseline, environment, and assumptions at execution time. Priority determines the choice among eligible plans.[THERE IS A LOT IN THIS PLAN WHICH CAN BE TO DO 'ED BECAUSE WHILE YES USEFUL, NOT REQUIRED FOR MVP1 BUILD ]

Separate readiness validation from scheduling. A plan can be ready but not due, or due but blocked by a missing requirement. [THIS WONT HAPPEN, I WILL TELL YOU FIRST THIS PLAN THEN THIS PLAN THEN THAT PLAN AND THEN THAT PLAN AND THEN THAT PLAN] 

## Dependencies and failed plans

If plan B requires plan A, B must use a recorded integrated checkpoint containing A. An automated-verification edge allows provisional continuation after A's automated gates pass; a human-acceptance edge also waits for approval. Provisional descendants remain explicitly unaccepted. If A is blocked, hold B. Independent plans can proceed from an eligible verified checkpoint according to queue policy. [THERE IS NO SCENRIO WHERE THIS WIILL HAPPEN, IN THE UI YOU ARE TO GIVE ME AN OPTION TO TELL YOU 1,2,3,4, ORDER OF EXECUTION FOR PLANS]

If A changes after B begins, preserve the old chain, carry the correction into a revised candidate, and reassess affected descendant assumptions and evidence. A conflict-free Git application does not establish semantic compatibility. See [06](06-workspaces-and-integration.md).

> **✅ DECISION C6 — Conservative invalidation, stack limit, rejection path** (accepted Oct 9; details to work through)  
> **Problem:** “affected” downstream work had no rule, provisional stacks were unbounded, and morning rejections had no path back in.  
> **Fix:** (1) **Invalidation:** any change to an upstream checkpoint marks **all** descendant evidence stale and reruns their full checks; this costs compute, not your time. An agent may propose a narrower set only with a recorded reason. (2) **Stack limit:** at most 2 unaccepted provisional plans stacked on each other; further dependents wait. (3) **Rejection path:** your morning feedback creates a new plan revision on the same item. Local corrections enter repair; behavior or interface changes return to Plan mode ([14](14-plan-refinement-and-local-backlog.md)), which triggers (1) for descendants.



[NO TO DECISION 6, I CAN STACK AS MANY PLANS AS I WANT TO ON TOP OF EACH OTHER, YOU DONT NEED TO WORRY ABOUT CHANGES TO THE CODE OF PLAN 1 AFTER PLAN 1 IS UPDATED IF IT IS CHANGES I WILL ASSUME THE CHANGE WA SREQUIRED FOR PLAN X EXECUTION AND BE FINE WITH IT, REJECTION PATH, MY MORNING REVEISION WILL BE A COMPLETELEY DIFFERENT PROJECT AND WONT BE CONCERNED WITH THIS, A NEW AGENT WITH A NEW DIRECTIO WILL BE SPUN UP AND EXECUTED, YOUA RE JUST EXECUTING TH EPLAN YOU ARE NTO MAINTINAING IT] 

Do not accidentally start an independent plan on partially repaired code from a failed plan.

## Ambiguity handling

Revised Oct 9 (D-29). Unclear criteria are found and closed in Plan mode ([14](14-plan-refinement-and-local-backlog.md)); that is the only place you are asked. At night the controller never holds a plan for a question: the agent interprets, proceeds, and records the interpretation, which leads the report [HOW DOES IT DO THAT, I WOUDL GUESS APLAN FOR EACH PLANS EXECUTION WHICH IS WRITTEN INTO AS WE ARE WRITIGN THE CODE]. A plan is still held by a dependency gate waiting for your acceptance (C6), which is not a question.

## Exploration

- Which dependency edges require human acceptance, and which may proceed provisionally? [DEPENDENCY EDGES ?]
- Can plans be added while a run is active? [NO]
- Should queue order be strict or allow skipping blocked entries? [STRICT]
- How should plans across different repositories be prioritized? [THEY WONT BE, RIGHT NOW ONE PLAN ONE REPOSTIROY, THIS IS FOR LATER NOT FOR NOW] 

