"""Local filesystem storage for the podcast tools.

Text artifacts — transcripts, summaries, chat logs — are written by calling the
CRUD MCP tools (``file_create`` / ``file_update``) directly, so every file the
pipeline produces goes through the same tools the agent uses. They land in the
shared store (``podcast_tools/data/`` for now) as flat, category-prefixed names
like ``transcript__<id>.md``, where the agent can list and read them back.

Downloaded audio is a binary intermediate, not a final artifact, so it stays in
a local ``data/audio/`` cache written directly (the text CRUD tools don't handle
binaries).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
import re
from pathlib import Path
from typing import Optional

import filestore

# Audio is a binary intermediate — kept out of the text store.
DATA_DIR = Path(__file__).resolve().parent / "data"
AUDIO_DIR = DATA_DIR / "audio"
SHARED_ENV_PATH = Path.home() / "Documents" / "AI Code" / ".env"


def ensure_dirs() -> None:
    """Create the local audio cache (text artifacts use the shared store)."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def _artifact_name(kind: str, episode_id: str) -> str:
    """Flat, category-prefixed store name, e.g. ``transcript__yt_abc.md``."""
    return f"{kind}__{episode_id}.md"


def _save_via_tools(name: str, content: str, *, append_if_exists: bool = False) -> str:
    """Persist ``content`` to ``name`` by calling the CRUD MCP tools.

    Tries ``file_create`` first; if the file already exists, either appends
    ``content`` or overwrites the whole file. Imports the tools lazily so that
    importing this library never pulls in the server package (which would form a
    circular import). Returns the saved path.
    """
    # Lazy import: at call time the server package is fully initialised.
    from simple_server.tools.files import file_create, file_update

    result = file_create(name, content)
    if result.startswith("ERROR") and "already exists" in result:
        mode = "append" if append_if_exists else "overwrite"
        result = file_update(name, content, mode=mode)
    if result.startswith("ERROR"):
        raise RuntimeError(f"CRUD tool could not write {name!r}: {result}")
    return str(filestore.resolve(name))


def make_episode_id(url: str) -> str:
    """Stable id for a source URL: ``yt_<videoid>`` for YouTube, else ``ep_<hash>``."""
    yt_match = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", url)
    if yt_match:
        return f"yt_{yt_match.group(1)}"
    return "ep_" + hashlib.md5(url.encode("utf-8")).hexdigest()[:12]


def transcript_path(episode_id: str) -> Path:
    return filestore.resolve(_artifact_name("transcript", episode_id))


def summary_path(episode_id: str) -> Path:
    return filestore.resolve(_artifact_name("summary", episode_id))


def chat_path(episode_id: str) -> Path:
    return filestore.resolve(_artifact_name("chat", episode_id))


def read_markdown(path: Path) -> str:
    """Read a UTF-8 markdown artifact with a clear missing-file error."""
    if not path.exists():
        raise FileNotFoundError(f"Markdown artifact not found: {path}")
    return path.read_text(encoding="utf-8")


def read_header_field(text: str, field: str) -> str:
    """Return a value from the leading ``---`` front-matter block, or ``""``."""
    if not text.startswith("---"):
        return ""
    _, _, rest = text.partition("---")
    block, _, _ = rest.partition("\n---")
    for line in block.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == field:
            return value.strip()
    return ""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def markdown_header(**fields: str) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            continue
        safe_value = str(value).replace("\n", " ").strip()
        lines.append(f"{key}: {safe_value}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def write_transcript(
    episode_id: str,
    transcript: str,
    title: str = "",
    source_url: str = "",
    platform: str = "",
) -> str:
    """Write the raw transcript artifact and return its path."""
    header = markdown_header(
        artifact="transcript",
        episode_id=episode_id,
        title=title or episode_id,
        source_url=source_url,
        platform=platform,
        created_at=utc_timestamp(),
    )
    body = f"# Transcript: {title or episode_id}\n\n{transcript.strip()}\n"
    return _save_via_tools(_artifact_name("transcript", episode_id), header + body)


def write_summary(
    episode_id: str,
    summary: str,
    title: str = "",
    transcript_id: Optional[str] = None,
) -> str:
    """Write the summary artifact and return its path."""
    header = markdown_header(
        artifact="summary",
        episode_id=episode_id,
        transcript_id=transcript_id or episode_id,
        title=title or episode_id,
        created_at=utc_timestamp(),
    )
    body = f"# Summary: {title or episode_id}\n\n{summary.strip()}\n"
    return _save_via_tools(_artifact_name("summary", episode_id), header + body)


def append_chat_turn(episode_id: str, question: str, answer: str) -> str:
    """Append one Q&A turn to the persisted chat markdown and return its path.

    First turn creates the file (with header) via ``file_create``; later turns are
    appended via ``file_update`` — both through the CRUD MCP tools.
    """
    turn = (
        f"\n\n## {utc_timestamp()}\n\n"
        f"**Question:** {question.strip()}\n\n"
        f"**Answer:**\n\n{answer.strip()}\n"
    )
    header = markdown_header(
        artifact="chat",
        episode_id=episode_id,
        transcript_id=episode_id,
        created_at=utc_timestamp(),
    ) + f"# Chat: {episode_id}\n"

    # Lazy import: avoids a circular import when this library is loaded standalone.
    from simple_server.tools.files import file_create, file_update

    name = _artifact_name("chat", episode_id)
    result = file_create(name, (header + turn).rstrip() + "\n")
    if result.startswith("ERROR") and "already exists" in result:
        result = file_update(name, turn, mode="append")
    if result.startswith("ERROR"):
        raise RuntimeError(f"CRUD tool could not write {name!r}: {result}")
    return str(filestore.resolve(name))


def load_shared_env() -> None:
    """Load the shared assignment env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if SHARED_ENV_PATH.exists():
        load_dotenv(SHARED_ENV_PATH, override=False)
    load_dotenv(override=False)


def require_env(name: str) -> str:
    load_shared_env()
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it in {SHARED_ENV_PATH} or the current shell."
        )
    return value
