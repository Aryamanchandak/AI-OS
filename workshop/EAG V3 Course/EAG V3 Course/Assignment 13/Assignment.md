The assignment

First the code:

glc_v3
S13Code
S13Proof
Github Links:

glc_v3 << nothing to be done, just reference
S13Code << you need to open PR
Build one meaningful extension to glc_v3 and prove it through a use case. The extension may improve the live planner, memory, semantic indexing, or A2A federation. A submission without an end-to-end run does not score, even if its unit tests pass

Part 1: reproduce the floor

Run the test suite and the non-browser benchmark. Pick four cases: one live expansion, one durable-memory round trip, one semantic document query, and the A2A waiting/resume case. For each, retain the prompt, graph, ordered event trace, provider/agent assignments, evidence, and final answer.

Then explain one honest limitation the trace exposed. “No limitation” means the trace was not read carefully.

Part 2: extend one boundary

Choose one track.

Live graph track. Add an outcome-driven behavior that the current planner cannot express well: speculative work with deterministic cancellation, a human-approval wait, a quorum, a retry policy that distinguishes transient from permanent failure, or a budget-aware branch. Prove that future nodes do not exist before their inputs and that cancelled work does not leak a late result into the graph.

Memory track. Add a reviewed promotion path, expiry/forgetting workflow, contradiction handling, retrieval evaluation, or a new scoped backend. Prove a write, an authorized recall, a denied cross-scope recall, a correction with preserved history, and provenance in the final answer.

Semantic indexing track. Improve extraction for a real document type, add a retrieval benchmark, or strengthen boundary handling without changing Rohan V2's suffix-rollover invariant. Prove exact source coverage, no overlap, idempotent re-indexing, rollback on injected failure, and better retrieval on at least ten labeled queries against a fixed-word baseline.

A2A track. Connect a second framework or language through A2A 1.0, add verified signed-card trust policy, or implement a durable push receiver. Prove discovery, version/binding negotiation, authentication failure, task progress, completion artifact, cancellation, duplicate push suppression, process restart, and that the remote agent cannot retrieve local memory outside the explicit task context.

Part 3: attack your own claim

Write one adversarial test against the exact feature you added. Try a duplicate event, stale document version, wrong tenant, malformed model patch, paraphrased semantic suffix, tampered card, replayed webhook, or result arriving after cancellation. Show the failure before the fix and the same attack failing afterward.

What you submit

Submit one pull request and one README section inside it. Do not create a folder of explanatory reference documents.

The README section contains:

the user-visible capability in one paragraph,
the exact prompt or API request,
the graph and ordered event trace,
the actual final result,
the evidence and provider/agent assignments,
the adversarial failure and fix,
the commands that reproduce everything from a fresh checkout.
Secrets, .env, raw credentials, personal memory, and unrestricted local paths never enter the pull request. Synthetic test identities are mandatory.

