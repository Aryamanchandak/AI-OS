# Job 5: small cleanup

Date: 2026-11-12. Status: outline only, nothing implemented. Can run any time; none of it blocks the other jobs.

## What

Remove code nothing uses and fix comments and docs that describe a system that no longer exists. Each item is its own small commit so you can review it in one sitting.

## Unused code

`find_cover` in `sources/book_metadata.py` is defined and never called; the Decision Register already says to delete it. `sources/markdown_tree.py` (42 lines) is imported by nothing except its own test, `test_sources_markdown.py`. I will confirm each with a search before deleting and list the test deletion for your approval.

## Stale comments

The header of `runner.py` points at a plan file that was deleted on 13 October. `config.py` still names its function `ai_code_root` although it now finds `AI OS`; renaming it touches `test_config.py` and two callers. `scripts/configure_local_neo4j.py` still says `AI Code/.env` in its header.

## Stale docs

`Ingestion 2 — Decision Register.md` shows the Graphiti decision and the gateway decision as open. You closed both in your comments on the Graphiti plan. `gateway/docs/plans/README.md` says ingestion still loads `llm_gateway` on port 8107; that stopped being true in commit 9829b3b.

## Left from job 1

There is no `.env` at `AI OS/`, so the gateway token is not loaded. You create that file; I do not handle the token. Once it exists, `scripts/live_smoke.py` makes the first real ingestion call through the gateway, which has never been proven.

## Done when

A search finds no caller-less function from this list, no mention of `llm_gateway` or port 8107 outside archived folders, and all tests pass.

## Needs your answer before starting

Four chat profiles in `gateway/config/profiles.yaml` are not named anywhere in the ingestion code: image transcription, highlight-photo summary, OCR cleanup and spelling review. Are they for another project, or left over? I have not checked how the spelling and OCR code picks its model, so this may be a false alarm.

## Not in this job

Docling for file intake and the choice of chunker. Both are still open in the Decision Register and wait until Graphiti is in.
