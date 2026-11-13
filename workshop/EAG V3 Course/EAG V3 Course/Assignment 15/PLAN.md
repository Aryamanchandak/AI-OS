# Research and Learning Assistant

Build one assistant that uses supplied documents to produce cited decision briefs and help you study the underlying material. Extend the existing Assignment 15 runtime and gateway.

## Research flow

Take a research question and supplied documents, extract relevant evidence, compare competing explanations, and produce a cited decision brief. The brief should distinguish supported conclusions from uncertainty. Record the models used and their costs.

## Learning flow

Once the research flow works end to end, use the same documents to generate source-backed study cards. Accept your recall answers and grade them as correct, partial or incorrect, with explanations grounded in the sources.

## Assignment evidence

Evaluate the research workload on at least 15 real tasks with success criteria you define. Compare cheaper-model routing with always using the top model. Report answer quality, cost per call, cost per resolved task, the break-even resolution rate, and at least one bad routing decision with its cost.

Run both supplied test suites and the five required proofs. Capture four runs with their prompts, selected tiers and models, ordered events, Jaeger trace IDs, ledger rows and final answers. Include one honest limitation and an adversarial test showing spending before control and a visible refusal after control. Record reproducible commands and results in the README evidence section.

## Next implementation step

You provide one real research question, its source documents and what a good answer should contain. Turn that example into tests first, then implement the smallest complete research flow using the existing infrastructure. Verify it on those documents before adding the learning flow. Ask before adding dependencies or changing the AI OS trunk.

The first increment is ready for review when the research flow produces a brief that meets your example, its citations can be checked against the supplied documents, its model calls and costs are recorded, and the relevant tests pass. Show the actual output and code for your review before committing.
