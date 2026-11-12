# Personal AI OS — Plain English Project Plan (Draft for Approval)

## What we are making

We are building a personal AI OS that helps Aryaman use AI across his real work and life while keeping him involved in the thinking and decisions. It should understand his goals, priorities, knowledge, open decisions, recurring work, and decision history. It should bring that context to the right specialist, help reveal what is missing or uncertain, and support useful actions and automation.

The central idea is to make AI improve decision quality over time, not just produce answers quickly. Before receiving decision help, Aryaman records his own claim, confidence, and reasoning. The system then checks the relevant evidence and prior context, tests understanding, surfaces counterarguments and gaps, and leaves the final decision with him. Later, recorded outcomes can show where his judgments are becoming better calibrated and where he has recurring blind spots.

This is an AI OS, not only a judgment checker. Its wider direction includes agents that can operate on files and computer tasks, automate recurring manual work, react to events, and connect work across the user's personal systems. Graph-based agents and proactive prompts are areas to explore. The capstone is a focused, working slice of this larger system, using the existing code and shared infrastructure wherever they prove dependable.

## What the capstone should prove

The capstone should show one real work decision moving through the AI OS as a connected workflow. The system should:

1. Capture the user's initial judgment, confidence, and reasons before showing its assessment.
2. Route the request to the relevant specialist or specialists.
3. Gather useful evidence from the user's own knowledge base and decision history.
4. Check the user's understanding and surface meaningful counterarguments, missing context, or uncertainty.
5. Consider relevant goals, priorities, calendar, and backlog when the question is about what to do.
6. Explain what evidence it used, what it inferred, and what it could not establish.
7. Abstain or identify a gap when its specialists and evidence cannot support an answer.
8. Let the user make the final call and record the decision so its outcome can inform future judgment.

The product's value is the connected use of the user's own context, memory, specialist agents, and learning history—not the router by itself.

## How it should work

- The existing React shell is the human-facing surface.
- The existing FastAPI gateway is the authenticated front door.
- A central Main Loop / planner receives each request, assembles context, and decides which specialist calls are useful and in what order.
- Specialists do their own domain work and return results to the Main Loop. They do not call one another directly; the Main Loop passes information between them when needed.
- The shared data and memory stores are accessed through defined query paths, rather than being browsed directly by the interface.
- The system records a trace of the request, specialist calls, evidence, uncertainty, and user decision so a workflow can be reviewed and replayed.

This follows the architecture notes, which identify the existing `AI Agent` loop as the Main Loop and keep the shell, gateway, planner, specialists, and data layer in distinct roles. Some integration details remain open and should be settled during the first implementation pass.

## The example decision workflow

The five questions in the pitch are useful ways to describe the product, but the demo should feel like one decision rather than five unrelated prompts:

1. The user records what they currently believe, how confident they are, and why.
2. The system identifies the claims and context that matter to the decision.
3. Research/verification checks those claims against the user's accumulated knowledge and supporting sources.
4. Understanding diagnosis checks whether the user's explanation reflects real understanding, not just familiarity with terms.
5. Steelman finds the strongest case against the user's current view.
6. Decision Tracker retrieves related past predictions and records the current confidence for later calibration.
7. If the decision concerns today's priorities, the system considers the calendar and backlog.
8. The Main Loop brings the results together, distinguishes evidence from inference, points out gaps, and returns the decision to the user.
9. When the real outcome becomes known, it is recorded and can inform future calibration and practice.

The planner should call only the specialists that fit the decision and make that routing understandable. The five questions remain a working product frame, not a frozen specification.

## Step-by-step plan

### Step 1 — Agree on the product and capstone boundary

- Approve this description of the long-term AI OS and the smaller capstone slice.
- Choose the real work decision that will anchor the demonstration.
- Confirm which questions and behaviors are essential to that demonstration.
- Keep the larger AI OS direction visible without requiring every future capability to be built for the capstone.

### Step 2 — Establish what already works

- Identify the canonical Main Loop, gateway, shell, shared model gateway, data root, memory stores, and specialist implementations.
- Run candidate specialists against real stored data and record what each can reliably do.
- Separate components that can be used now from those needing a bounded repair or a later rebuild.
- Confirm that the data and specialist code needed for deployment are included in the tracked project.

### Step 3 — Get one real end-to-end path running

- Connect the shell to the authenticated gateway and the gateway to the Main Loop.
- Have the Main Loop call one proven specialist using real data.
- Return an evidence-bearing response and save a trace of the workflow.
- Deploy this thin working path to a real URL early, so deployment problems are found before the end.

### Step 4 — Add the core decision checks

- Preserve the user's initial judgment, confidence, and reasoning before revealing feedback.
- Add the chosen research/verification, counterargument, and calibration capabilities through the Main Loop.
- Build or integrate the understanding-diagnosis capability needed to detect fluent but incorrect explanations.
- Make the response distinguish retrieved evidence, system inference, uncertainty, and unsupported gaps.

### Step 5 — Include priorities and real-life context

- Connect the workflow to the user's goals, priorities, calendar, and task backlog where they improve the chosen decision.
- Reuse existing calendar/backlog code if it can work reliably in the deployment setup; otherwise define a narrow input that keeps the demo dependable.
- Treat continuous, event-triggered action as part of the broader AI OS direction; only include it in the capstone if the basic deployed decision workflow is already reliable.

### Step 6 — Make the system learn from outcomes

- Save the initial confidence, checks, decision, and eventual outcome in a form that can be retrieved later.
- Connect these records to Decision Tracker's calibration measures by decision type.
- Show how repeated use could reveal overconfidence, recurring blind spots, or improvement.
- Keep automated changes to how much help the system gives as a future step until there is enough trustworthy history.

### Step 7 — Challenge the workflow with difficult inputs

- Check whether it rejects a source that merely claims it was already fact-checked.
- Check whether it catches a fluent explanation that contains a subtle error.
- Check whether misleading wording or a false urgency signal can send the request to the wrong specialist or bypass needed checks.
- Make sure it shows uncertainty or abstains when the evidence is insufficient.

### Step 8 — Prepare a clear demonstration

- Run the chosen real decision through the deployed system from initial commitment to final user decision.
- Keep a replayable trace showing the context used, routing, specialist results, evidence, confidence, gaps, and final decision point.
- Confirm that the workflow survives the difficult inputs above.
- Prepare and rehearse the five-minute pitch around the problem, the personal AI OS foundation, the connected decision workflow, and what the demo proves.

## What is in the larger direction, beyond the first capstone slice

The plan should preserve these as parts of what the AI OS can become, without assuming they all fit into the capstone deadline:

- Proactive detection of missing nuance and recurring blind spots.
- Practice scenarios that let the user build judgment through repeated, low-cost exercises.
- Causal graph agents for exploring how work situations may unfold.
- Spaced reminders that bring back specific misconceptions or weak areas when useful.
- Agents that respond to events and carry out approved recurring work.
- Computer-use and coding agents that can work with files and applications.
- Gradually reducing assistance as the user's demonstrated calibration improves.
- Extending the same personal system to a local AI computer as that becomes available.

## Items to settle while approving this plan

These are discrepancies or choices present in the source documents, not decisions this draft assumes:

1. **Which specialists are in the first demonstrated workflow?** The PPT names four existing specialists as live today, while the four-week build plan says to select three dependable specialists and separately build understanding diagnosis. Confirm whether the intended build is three existing specialists plus the new capability, or a different combination.
2. **When exactly does commitment happen?** The deck says the user commits before being checked, while its final deliverable wording can be read as checks before a committed judgment. This draft interprets commitment as happening first: initial claim, confidence, and reasoning are captured before feedback.
3. **How much of calendar and backlog is in the capstone?** The pitch includes them. The planning notes point to an existing Apple Calendar/Reminders integration but flag deployment constraints. Confirm whether live integration is required for the first demo or whether a dependable, bounded input is acceptable initially.
4. **How much autonomy is demonstrated?** The broad AI OS includes event-triggered agents and automation. The four-week plan is centered on a user-initiated decision workflow. Confirm that the capstone proves the core workflow first, while event-triggered action remains part of the wider direction unless it is already safe and reliable to include.
5. **Product name and one-line description.** The PPT uses “Judgment Gate” as the judgment core of the personal AI OS. The planning docs contain alternate names and descriptions. Confirm whether to use the PPT framing as the current version.

## Draft success condition

The capstone is successful when a real, deployed workflow helps the user examine one consequential work decision using relevant personal context and working specialists; preserves the user's initial judgment; makes its evidence, uncertainty, and gaps visible; handles the agreed difficult inputs; records the user's final decision and eventual outcome; and can be demonstrated through a replayable trace.

---

This is a plain-English product and project plan for review. The next step, after approval and any corrections, is to turn it into concrete deliverables, owners, dependencies, and completion checks.
