---
name: Podcast Agent Architecture
description: Core architecture of the Podcast-Agent project — two-layer design with orchestrator.py as backend and app.py as Streamlit UI
type: project
---

This is a podcast summarisation system. The pipeline is: RSS feed → audio download → Deepgram transcription → Gemini summarisation → Markdown file output.

**Key architectural facts:**
- `orchestrator.py` is the entire backend. It is importable by `app.py` and also runnable as a CLI.
- `app.py` is a thin Streamlit UI that delegates all work to `orchestrator.py`.
- `podcast_v1.py` is a self-contained reference implementation kept for comparison — not imported anywhere.
- `podcasts.yaml` is the only way to add RSS feeds — no UI for it.
- `output/transcripts/` and `output/summaries/` hold persisted Markdown outputs.
- `tmp/audio/` and `tmp/transcripts/` hold intermediate files that are never deleted.

**Why:** The refactor split the monolithic v1 into a clean orchestrator + UI pattern to support both CLI and web modes.

**How to apply:** When suggesting changes, route business logic to `orchestrator.py` and display changes to `app.py`. Keep `podcast_v1.py` as-is.
