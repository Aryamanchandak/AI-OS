# `file_upload`  ·  group: `utility`

1 registered MCP tool(s). Everything for this tool lives in this folder.

### `upload_file_to_gemini(source: str) -> dict[str, str | None]`

Upload one local sandbox file to the Gemini Files API and return reusable
Gemini file identifiers.

Decisions:
- Accepts only a filename or sandbox-relative file path.
- Does not accept absolute local paths.
- Does not download HTTP/HTTPS URLs.
- Waits until Gemini marks the uploaded file `ACTIVE`.
- Returns both `name` and `uri`; downstream tools should usually pass `uri` as
  `file_uri`.

Return shape:

```json
{
  "name": "files/...",
  "uri": "https://generativelanguage.googleapis.com/...",
  "mime_type": "...",
  "display_name": "..."
}
```

**Files:** `logic.py`, `__init__.py` (registration).
