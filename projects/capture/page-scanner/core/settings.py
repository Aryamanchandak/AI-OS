"""Shared paths for the drop-folder ingest + Raw Data publish wiring.

All three locations are env-overridable so the pipeline can be pointed at test
dirs without touching code:

  PS_SOURCE_DIR    the drop folder you put book photos into
  RAW_DATA_ROOT    the data-lake root the reviewed output is published into
  HG_DB            the processed.db the processor/cockpit share (see server.py)

The defaults are the real machine paths so a bare `python ingest.py` just works.
"""

from __future__ import annotations

import os
from pathlib import Path

# The drop folder. Each *subfolder* inside is one book (its name / book.txt is
# the title we resolve metadata from). Photos go inside the book subfolder.
SOURCE_DIR = Path(
    os.environ.get(
        "PS_SOURCE_DIR",
        "/Users/aryamanchandak/Desktop/Page Scanner",
    )
).expanduser()

# The Raw Data lake root (the folder that contains bronze/, lib/, backups/…).
RAW_DATA_ROOT = Path(
    os.environ.get(
        "RAW_DATA_ROOT",
        "/Users/aryamanchandak/Documents/AI Code/Database/Raw Data",
    )
).expanduser()

# The source slug we registered in Raw Data's lib/config.py SOURCE_REGISTRY.
RAW_SOURCE = "highlight"

# Where the shared processed.db lives (kept in sync with server.py's default).
_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("HG_DB", str(_ROOT / "data" / "processed.db")))
