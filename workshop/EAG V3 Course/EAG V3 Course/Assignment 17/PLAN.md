# Assignment 17 — Financial Tool Builder

## Goal

Build a standalone app that turns a plain-English request or a document containing financial calculation rules into a working, tested interface. Users operate through prompts and previews; reading code is optional. This coursework product stays separate from AI OS.

## Two ways to build

**Prompt to financial tool.** Describe the inputs, calculation and desired result. The app shows its interpretation and unresolved assumptions, then uses S17Code to generate the interface. Follow-up prompts modify the tool.

The first example is a portfolio rebalancing calculator: holdings, prices, target weights and new cash go in; proposed trades and resulting allocations come out. Confirm rules such as selling, fractional units, fees and cash treatment before generation. This calculates user-specified allocations; it does not choose investments.

**Document to calculator.** Supply a document containing formulas or calculation rules. The app presents the extracted rules with source passages for review, then uses the confirmed interpretation to generate the calculator. Missing or conflicting rules must be surfaced before building.

The first example is a fee calculator built from a supplied fee schedule. Confirm details such as tiers, calculation period, minimum charges and rounding. Choose the initial document format from the real sample before adding extraction dependencies.

## User experience

One workspace contains the request or document, the interpreted rules, the generated tool preview and an expandable activity panel. Users can enter values, inspect results, request changes and download the finished standalone HTML tool.

The activity panel displays actual engine events: task nodes appearing, commands executing, checks failing, fixes being attempted and final results. Failures remain visible with their reason. A disconnected engine must show an error rather than simulated progress.

## Engine and boundaries

S17Code is the coding engine: https://github.com/theschoolofai/S17Code

glc_v5 handles model access and credentials: https://github.com/theschoolofai/glc_v5

Inspect the actual repositories before choosing integration details. The lecture describes run creation, event streaming and graph snapshots, but their request and response formats still need verification. Keep engine integration behind one thin adapter.

Documents are untrusted input. Their contents cannot authorize commands or edits. Generation begins only from the user's confirmed request, within an isolated workspace with bounded execution and protected checks. Credentials come from `.env`; never expose them to generated tools or browser code.

## Immediate implementation scope

After the course repositories are available locally, inspect their interfaces and run their existing tests. Ask before adding dependencies. Obtain one real example with known answers for each route, and encode those answers as tests before implementation.

Build the two routes around the same minimal generation and preview flow. Verify each route on its real example before connecting it to the shared interface. Support one HTML output per request; keep execution isolated from the host app and credentials.

## Done when

Both example requests produce usable tools through S17Code, with confirmed rules and correct outputs for the supplied examples. Follow-up prompts update the preview without silently dropping agreed requirements. Generated tools can be downloaded and opened independently.

Demonstrate a genuine failed check followed by a repair and passing check, plus an unsuccessful run with an explicit reason. Preserve the visible execution history and report actual verification output.

For the assignment's separate bug requirement, reproduce a real S17Code or glc_v5 bug, add a test that fails before the fix and passes afterward, and prepare the fix for Aryaman to submit upstream. Do not invent a bug or weaken an existing test.

Finish with a runnable README, an honest account of agent-written and Aryaman-written work, and material for the demo video. Show changes and test output for review before committing; Aryaman handles upstream pull requests and authorizes any push.
