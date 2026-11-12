# Raw Chat Storage

This folder stores raw chat transcripts captured automatically from
agent-facing systems before they are summarized, embedded, converted into graph
facts, or used for memory.

## Purpose

Raw chats are the source-of-truth record of what was said. Writing them is a
mandatory runtime side effect, not an MCP tool and not a model-selectable action.
Downstream systems can derive summaries, memories, vectors, or graph entities
from these records, but the original exchange stays here for audit and replay.

## Stored Records

Each conversation must be stored as an immutable markdown or JSONL artifact
with metadata that makes the origin and routing clear:

- conversation id
- source application or agent surface
- capture timestamp in UTC
- participant roles
- model and provider when a model response is involved
- tool calls requested by the model
- tool results returned to the model
- raw user and assistant messages
- links to any gateway call ids or tool event ids

## Recommended Layout

```text
chats/
├── README.md
└── bronze/
    └── YYYY-MM-DD/
        └── <conversation-id>.jsonl
```

Use JSONL when preserving exact turn structure matters. Use markdown when the
chat is meant to be inspected primarily by a human.

## Capture Rule

Every chat request that reaches the gateway must produce a raw record here,
including failures. Keep operational counters and event indexes in SQLite, but
do not treat SQLite rows as the only copy of a conversation.
