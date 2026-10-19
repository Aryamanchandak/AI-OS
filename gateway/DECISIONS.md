# Decisions

- 2026-10-19 — Embeddings stay unlabelled (no `search_document:`/`search_query:`). Why: existing vectors came through gateways that drop the flag, and adding labels now would stop new vectors matching old ones; revisit only with a full re-embed.
- 2026-10-19 — Golden set has no image-transcription case. Why: no real image with known words yet; add one when there is.
- 2026-10-19 — `.env` is loaded when the app is created, and shell variables win over it. Why: `AI_OS_TOKEN` is read at import time, and an explicit shell export should beat a file.
