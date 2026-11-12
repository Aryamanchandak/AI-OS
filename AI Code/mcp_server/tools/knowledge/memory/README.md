# `memory`  ·  group: `knowledge`

2 registered MCP tool(s). Everything for this tool lives in this folder.

### `index_document(path: 'str', chunk_size: 'int' = 400, overlap: 'int' = 80) -> 'dict'`

Chunk a sandbox file or artifact and write each chunk into Memory as a searchable
`fact`. Use this when the content must remain retrievable across later turns or runs (an
indexing step before later vector queries). For one-shot inspection of a known file's
contents in this turn, prefer `read_file` instead. Example:
index_document("notes/spec.md").

### `search_knowledge(query: 'str', k: 'int' = 5) -> 'list[dict]'`

Vector search over indexed `fact` chunks. Returns up to k ranked chunks with provenance.
Call this rather than re-fetching URLs or re-reading source files whenever Memory
already contains indexed chunks for the topic — that is the whole point of having
indexed the corpus. Example: search_knowledge("authentication flow", 5).

**Files:** `tool.py`, `__init__.py` (registration).
