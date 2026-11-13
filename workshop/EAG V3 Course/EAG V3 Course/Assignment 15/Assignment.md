Session 15 - Assignment QnA
Due Sat, Aug 8, 2026 at 11:00 AM
1000 points
Resubmission allowed
The assignment

Build a routing and budget policy for a workload of your choosing, and prove what it costs.

Part 1: reproduce the floor

Run both suites and the five proofs. Capture, for four runs: the prompt, the tier and model chosen, the ordered event trace, the Jaeger trace ID, the ledger rows, and the final answer. Then state one honest limitation the traces exposed.

Part 2: build a policy and measure it

Choose a task class with at least fifteen tasks — your own domain, not the shipped file. Build a ladder and a budget policy for it. Then measure, against an always-frontier baseline:

cost per call and cost per resolved task, with a judge whose rubric you can defend,
the break-even resolution rate for your ladder from its measured spread,
at least one task where your policy chose wrongly, and what it cost.
A submission that reports only savings has not finished. Every routing policy trades quality for money somewhere, and finding where is the work.

Part 3: attack your own budget

Write an adversarial test against your policy. Drive a runaway loop, request an unaffordable tier, force a cascade to climb its whole ladder, or arrange for a provider to fail after consuming tokens. Show the spend before your control and the refusal after it, and show that the refusal is visible in your telemetry.

What you submit

A pull request to S15Code adding your policy, your task file, and one evidence section in the README containing:

the workload and the ladder you built for it,
the measured cost per call and cost per resolved task against the baseline,
your ladder's break-even resolution rate, and where you sit relative to it,
a Jaeger trace showing one run's span hierarchy with costs,
the adversarial test, failing before your control and refused after,
one case your policy got wrong,
the commands to reproduce all of it from a fresh checkout.
Secrets, .env, and real user data never enter the pull request.