# Agent Memory — Central Persistent Storage

This folder is the **single source of truth** for persistent memory for every Claude Code agent defined in `~/.claude/agents/`.

Each agent gets its own subfolder, named exactly after the agent (e.g. `code-archaeologist/`, `validation/`). Inside that subfolder live:

- **`MEMORY.md`** — a one-line index pointing to each memory file the agent has written. Always loaded into the agent's context.
- **Individual memory files** — one `.md` file per memory, named with a clear, descriptive convention (see below).

---

## Folder layout

```
~/Documents/AI OS/Persistent Memory Chats Storage/Agent Memory/
├── README.md                           ← this file
├── code-archaeologist/
│   ├── MEMORY.md
│   ├── user__<slug>.md
│   ├── feedback__<slug>.md
│   ├── project__<slug>.md
│   └── reference__<slug>.md
├── ideas-code/
├── overview/
├── red-team/
└── validation/
```

---

## File naming convention

Every memory file is named:

```
<type>__<descriptive-kebab-slug>.md
```

- `<type>` is one of: `user`, `feedback`, `project`, `reference`
- The double underscore (`__`) separates the type from the slug so it's visually obvious at a glance
- The slug should be **clearly descriptive** — multi-word, kebab-case, enough that a human can read the filename and know what's inside without opening it

### Good examples

```
user__role-data-scientist-streamlit-experience.md
feedback__prefer-narrative-prose-over-bullet-lists.md
feedback__simple-to-complex-progressive-explanations.md
project__streamlit-applescript-planning-assistant-stack.md
reference__linear-project-ingest-pipeline-bugs.md
```

### Bad examples

```
notes.md                  ← no type prefix, no descriptive slug
user_role.md              ← single underscore (collides with multi-word slugs), too vague
feedback1.md              ← no description, just a counter
project_x.md              ← what is x?
```

---

## Frontmatter inside each memory file

```markdown
---
name: <memory name>
description: <one-line description — used to decide relevance in future conversations, so be specific>
type: <user | feedback | project | reference>
---

<memory content — for feedback/project types, structure as: rule/fact, then **Why:** and **How to apply:** lines>
```

---

## MEMORY.md index format

`MEMORY.md` is the **index**, not a memory itself. It has no frontmatter. Each entry is one line, under ~150 characters:

```markdown
- [Title](file.md) — one-line hook describing what's inside
```

Keep it concise — lines after 200 may be truncated when loaded into the agent's context.

---

## Why this lives here

Previously each agent stored its memory in a project-local `.claude/agent-memory/` folder. That fragmented memory across every project the agent ran in. Centralising it here means:

1. An agent's accumulated knowledge persists across all projects
2. Memory is easy to inspect and curate from one place
3. Naming conventions stay consistent across agents
