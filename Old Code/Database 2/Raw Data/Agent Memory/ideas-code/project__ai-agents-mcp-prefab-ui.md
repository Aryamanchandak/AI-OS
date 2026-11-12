---
name: AI Agents MCP with Prefab UI
description: FastMCP server with 5 Prefab UI tools for financial AI agents at ICICI Prudential
type: project
---

Project path: /Users/aryamanchandak/Documents/ICICI Prudential/Code/Agents/Prefab UI/ai_agents_mcp/

Built a FastMCP server exposing 5 UI tools for financial AI agents, routed through Gemini intent classification.

## Tools built (all UI-only scaffolds, backends wired later)
- report_chatbot — company search combobox, document dropdowns (3 types), PDF drop zone
- meeting_recorder — audio recorder card with start/pause/stop/submit/clear buttons
- podcast_agent — DataTable with Audio component cells per sector row
- us_result_note — Morningstar PDF uploader card (up to 2 files, 5MB each)
- annual_report_analysis — 3-tab layout (AR Analysis, YoY, Peer-to-Peer) with URL input

## Architecture
- Each tool file exposes both `build_ui` (plain function alias) and `register(mcp)` (wraps with @mcp.tool(app=True))
- route_query tool uses Gemini 2.0 Flash to classify intent, calls tool_module.build_ui() directly
- config.py is the single source of truth for all data (empty placeholder lists until DB wired)

## Key prefab-ui API facts learned
- DropZone uses `description=` not `hint=`, and `max_size=` in bytes
- Tabs uses `value=` (not `default=`) for initial active tab; Tab takes positional `title`
- DataTable cells support arbitrary components (Badge, Audio, Row, etc.)
- Button icon: use `icon="kebab-case-lucide-name"` param, not nested Icon component
- Icon component: `from prefab_ui.components import Icon` with positional `name` arg
- OpenFilePicker: `from prefab_ui.actions import OpenFilePicker` — attach to Button on_click

## Status (as of 2026-05-20)
UI scaffold complete and all import/build checks pass. Backends not yet wired. GEMINI_API_KEY needed in .env for route_query to work.
