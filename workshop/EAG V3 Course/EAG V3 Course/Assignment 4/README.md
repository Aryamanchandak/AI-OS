# Assignment 4: a research notebook as an MCP server

An MCP server (a program that offers tools to an AI agent) with three tools:
one that uses the internet, one that edits a local file, and one that shows a
screen built with Prefab.

## The three tools

**`lookup_topic`** searches Wikipedia for a topic and returns the best page's
title, summary and link.

**`notes_file`** creates, reads, updates, deletes or lists notes in
`data/notes.json`. A note has a title, a body, a source link and a status of
`unverified` or `verified`.

**`show_notebook`** returns a Prefab dashboard of those notes: three counts, a
searchable table, a pie chart of verified against unverified, and buttons to
verify, delete or add a note. The buttons call `notes_file`, so the screen and
the file stay in step.

The code is four small files: `server.py` (the tools), `notes_store.py` (the
file), `ui.py` (the screen) and `preview.py` (a browser preview with sample
notes).

## Setup

```bash
uv sync
```

## Use it from an MCP host

Add this to the host's MCP config (for Claude Desktop, Settings → Developer →
Edit Config), with the real path to this folder:

```json
{
  "mcpServers": {
    "research-notebook": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/a04-mcp-prefab", "python", "/path/to/a04-mcp-prefab/server.py"]
    }
  }
}
```

## The prompt that forces all three tools

> Look up the ownership details of Tata Sons, save what you find as a note in
> my notes file with its source link, and then show me my notebook as a
> dashboard.

The agent has to call `lookup_topic`, then `notes_file` with `create`, then
`show_notebook`.

## Preview the screen without a host

```bash
uv run prefab serve preview.py
```

This shows sample notes. Selecting a row works; the buttons that call the
server do nothing here because there is no MCP host to carry the call.

## Tests

```bash
uv run pytest
```

The one test that needs the internet (a real Wikipedia lookup):

```bash
uv run pytest -m network
```
