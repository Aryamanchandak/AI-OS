# 2026-07-05 Shared Gemini File Upload Change Log

This note records the approved `shared/` block changes around Gemini file handling.

## Decisions Captured

- Keep one MCP-facing Gemini Files API upload tool.
- The upload tool accepts only local files already present in the server sandbox.
- Do not support HTTP/HTTPS download-and-upload behavior yet.
- Return both Gemini identifiers:
  - `name`, e.g. `files/...`
  - `uri`, passed to downstream tools as `file_uri`
- Keep raw PDF bytes as a narrow internal path for specific PDF workflows, not as a
  general MCP upload tool.

## Code Changes

### `shared/backend_utils.py`

- Added `gemini_api_key()` and `make_gemini_client()` for consistent Gemini client
  setup.
- Added `gemini_file_name(...)` so downstream tools can resolve a Gemini file from a
  full URI, `files/...` name, or bare file id.
- Kept `get_gemini_file(...)` as the lookup helper used by downstream analysis tools.
- Added `wait_for_gemini_file_active(...)` for Files API upload polling.
- Added `pdf_bytes_part(...)` as the PDF-only inline bytes helper.
- Removed the older unused `upload_pdf_to_gemini(...)` helper.

### `tools/utility/file_upload/`

- Replaced the old `upload_file(file_path) -> str` registered tool with
  `upload_file_to_gemini(source) -> dict`.
- The tool now returns `name`, `uri`, `mime_type`, and `display_name`.
- The tool rejects HTTP/HTTPS URLs and absolute/local paths outside the sandbox.

### `tools/utility/gemini/`

- Removed the duplicate URL-capable Gemini upload tool package.

### Downstream Tool Docs

- Updated file URI docstrings and READMEs to point callers to the `uri` returned by
  `upload_file_to_gemini`.
- Updated lease deed PDF byte handling to use the shared `pdf_bytes_part(...)`
  helper.

## Verification

- Compiled the touched Python files with:
  `UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m py_compile ...`
- Verified `gemini_file_name(...)` normalizes all supported reference forms to
  `files/...`.
- Verified `pdf_bytes_part(b"")` raises `ValueError`.
- Verified isolated utility-group registration exposes 10 utility tools and includes
  `upload_file_to_gemini`, with no `upload_file` or `upload_to_gemini`.
- Verified `upload_file_to_gemini("")` and an HTTP URL both raise before any upload.

Full `import tools` remains blocked in this sandbox because the sibling `agent/`
directory expected by `mcp_server.py` is not present, causing the knowledge memory tool
to fail on `import memory`. That blocker is unrelated to this block.
