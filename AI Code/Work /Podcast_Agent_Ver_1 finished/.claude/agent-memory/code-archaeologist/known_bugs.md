---
name: Known Bugs and Gaps — Podcast Agent
description: Confirmed bugs and architectural gaps in the Podcast-Agent codebase, found during 2026-05-10 documentation pass
type: project
---

Confirmed bugs and gaps found during code archaeology (2026-05-10):

1. **Same-day filename collision**: `_output_slug()` uses `%Y%m%d` (date only). Two runs of the same podcast on the same day silently overwrite each other's `.md` output files.

2. **Dead code in orchestrator.py**: `_is_youtube()` (line 228) is defined but never called — YouTube was dropped in the refactor. `import time` (line 10) is also unused.

3. **Dead code in app.py**: `on_progress()` function and `progress_log` list (lines 136–139) are defined but never used. The real progress display is the inline lambda on line 152. `from datetime import datetime` (line 6) is also unused.

4. **Transcript cache does not invalidate on model/option changes**: Cache key is `SHA-256(file) + diarise_flag` only. Changing `model="nova-3"` or any `PrerecordedOptions` returns stale cache silently.

5. **API key check asymmetry in app.py**: The startup check inspects `GEMINI_API_KEY` for a `"your_"` prefix but does not check `GOOGLE_API_KEY`. A user who sets only `GOOGLE_API_KEY` (valid alias accepted by the pipeline) is blocked at startup.

6. **Entire audio file loaded into RAM for transcription**: `f.read()` on the full file before Deepgram call. At 500 MB limit this is 500 MB of heap.

7. **No cleanup of `tmp/audio/`**: Downloaded files accumulate indefinitely.

8. **All paths are relative to cwd**: Running the script from a different directory creates orphaned `tmp/` and `output/` trees.

9. **No `.env.example` file**: `podcast_v1.py` error message references one that doesn't exist.

**How to apply:** When a user asks why something isn't working or asks what to fix next, reference this list.
