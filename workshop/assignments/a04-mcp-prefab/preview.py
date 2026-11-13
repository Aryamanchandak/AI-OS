"""Preview the notebook screen in a browser without an MCP host.

    uv run prefab serve preview.py

Shows sample notes. Buttons that call the server do nothing here, because
there is no MCP host to carry the call.
"""

from ui import build_notebook

SAMPLE = [
    {"id": "a1", "title": "Tata Sons ownership", "body": "Tata Trusts hold about 66% of Tata Sons.",
     "source_url": "https://en.wikipedia.org/wiki/Tata_Sons", "status": "verified",
     "created_at": "2026-11-13T10:00:00+00:00"},
    {"id": "b2", "title": "Bond duration", "body": "Modified duration estimates price change per 1% yield move.",
     "source_url": "", "status": "unverified", "created_at": "2026-11-13T10:05:00+00:00"},
    {"id": "c3", "title": "Shannon entropy", "body": "Entropy measures the average information in a source.",
     "source_url": "https://en.wikipedia.org/wiki/Entropy_(information_theory)", "status": "unverified",
     "created_at": "2026-11-13T10:09:00+00:00"},
]

app = build_notebook(SAMPLE, {"total": 3, "verified": 1, "unverified": 2}, topic="Sample")
