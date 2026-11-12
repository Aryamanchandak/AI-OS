# Study System Planning Set

**Created:** 2026-07-14  
**Source:** Follow-up comments in `REDESIGN_PLAN_v4_FOR_REVIEW.md`  
**Status:** Planning only; no implementation is authorized by these documents.

This folder replaces the attempt to keep every architectural decision and feature in one redesign document. The annotated source document remains the record of the user's comments. These files resolve the comments into smaller plans with clear ownership and sequencing.

## Documents

| Order | Document | Purpose | Intended owner |
|---:|---|---|---|
| 0 | `00_RESOLVED_MVP_AND_ARCHITECTURE.md` | Defines the first useful study-system and answers the cross-cutting comments | Study-system |
| 1 | `01_PRESERVATION_AND_MIGRATION.md` | Preserves working code, prompts, data, and behavior during redesign | Study-system plus affected owners |
| 2 | `02_STUDY_AUTOMATION_MCP_AND_CONFIG.md` | Plans the headless automation engine, MCP tools, safe overrides, and shell launcher | Study-system |
| 3 | `03_UNIFIED_INGESTION_PIPELINE.md` | Hands scanning, cleaning, hashing, extraction, and fan-out to a dedicated ingestion system | Ingestion project |
| 4 | `04_KG_IDENTITY_ALIASES_AND_EVOLUTION.md` | Plans identity, alias links, query expansion, feedback, and changing beliefs | Knowledge-graph project |
| 5 | `05_INTERFACE_AND_FEATURE_BACKLOG.md` | Separates shippable later features and records their order without designing them prematurely | Multiple projects |
| 6 | `06_COMMENT_RESOLUTION_LEDGER.md` | Tracks how review comments were resolved across the planning set | Multiple projects |
| 7 | `07_MVP_IMPLEMENTATION_VERIFICATION.md` | Records implemented MVP components, automated evidence, and remaining production checks | Study-system |
| 8 | `08_MCP_SURFACE_RECONCILIATION.md` | Resolves the two-MCP-exposure open item from document 7 §8: canonical path, tool-surface changes, verification | Study-system plus `mcp_server` project |
| 9 | `09_MCP_ADAPTER_RELOCATION.md` | Supersedes document 8's "keep both" compromise: physically moves the MCP adapter/server out of this repo into `mcp_server`; this repo is now a pure library | Study-system plus `mcp_server` project |

## Processing order

1. Approve the MVP boundary in document 00.
2. Create characterization tests and an asset inventory using document 01.
3. Implement the core study service, automation runner, MCP adapters, and configuration controls from document 02.
4. In parallel or afterward, design the upstream ingestion replacement from document 03.
5. Refactor KG identity only through the deeper design in document 04; do not improvise semantic merges inside study-system.
6. Select later features from document 05 one at a time and give each its own implementation plan when promoted.

## Non-destructive rule

Nothing currently working is deleted merely because its ownership changes. A capability may be retired only when:

1. its existing behavior and data have been inventoried;
2. the replacement owner and interface exist;
3. old data remains readable or has a tested migration;
4. characterization and replacement tests pass;
5. an end-to-end acceptance run succeeds; and
6. the old path is archived or removed in a separate, reversible change.

## Current first target

The first target is **not** a standalone study dashboard and **not** phone HTML synchronization. It is:

> A reusable study engine with a headless automation runner and MCP tools, invoked from the unified chat interface, with all persistent data stored under the central Database root.

The shell script is a launcher for automation. Terminal prompts and terminal review screens are not part of the target user experience.
