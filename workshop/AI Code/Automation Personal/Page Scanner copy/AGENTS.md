# Highlight Grabber — Project Memory

## Stack
- Python 3.11+, venv at .venv/
- ocrmac (Apple Vision OCR), opencv-python, pillow, pillow-heif, numpy
- FastAPI + uvicorn for the review cockpit
- SQLite via stdlib sqlite3 (no ORM)

## The core rule
Process first (headless, slow), review second (instant, precomputed).
The cockpit never waits on OCR — everything it shows is already in the DB.

## Key non-negotiables
- EXIF orientation applied on every image load. Non-negotiable. Silent failure otherwise.
- pillow-heif for HEIC. iPhone default format — skipping it breaks the whole inbox.
- Per-image try/except in the processor. One bad file must never kill the batch.
- file_hash dedup. Re-running the inbox must be safe and idempotent.
- edited_text flushes to markdown immediately on accept. The DB is disposable; typed edits are not.

## Keyboard model (cockpit)
- Cmd+Enter → accept + advance (works from inside a textarea)
- → → advance without saving (skip; page stays 'new')
- ← → previous page (editable back-nav)
- Tab → jump between passage fields
- d → discard | f → flag retake
- All single-key shortcuts fire only when focus is NOT in a textarea

## Parked — do not implement
- VLM / Ollama integration
- Handwriting / margin notes
- Multi-book management UI
- Readwise API push (CSV export is Phase 4)
- Auto color detection
- Two-page spread splitting

## Phases
- Phase 0: spike script only — validate OCR + mask + grouping, no production code
- Phase 1: MVP processor + cockpit, no quality gate, no drag-box, no page numbers
- Phase 2: quality gate + confidence flagging + per-batch color sampling
- Phase 3: drag-box fallback + page number capture
- Phase 4: Readwise CSV export (optional)