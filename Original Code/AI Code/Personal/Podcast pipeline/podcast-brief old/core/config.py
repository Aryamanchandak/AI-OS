"""
config.py — Shared configuration, model constants, and config loaders.
One source of truth for the rest of the codebase.
"""

import os
import yaml
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, computed_field

# ─── Model selection ─────────────────────────────────────────────────────────
# Use Opus for high-stakes synthesis where quality matters most.
# Use Sonnet for structured extraction and comparisons.
# Use Haiku for light tasks like speaker name resolution.

MODEL_SYNTHESIS = "claude-opus-4-5"
MODEL_EXTRACT = "claude-sonnet-4-5"
MODEL_LIGHT = "claude-haiku-4-5"

# ─── Paths ───────────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"

DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data")))
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
BRIEF_DIR = DATA_DIR / "briefs"
EXTRACTION_DIR = DATA_DIR / "extractions"
RESEARCH_DIR = DATA_DIR / "research_items"


def ensure_dirs():
    for d in (DATA_DIR, AUDIO_DIR, TRANSCRIPT_DIR, BRIEF_DIR, EXTRACTION_DIR, RESEARCH_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ─── Show config ─────────────────────────────────────────────────────────────

class ShowConfig(BaseModel):
    name: str
    profile: str = "hybrid"   # academic | current_events | hybrid
    rss: Optional[str] = None
    youtube_channel: Optional[str] = None
    speakers_hint: str = ""
    active: bool = True

    @computed_field
    @property
    def slug(self) -> str:
        """URL-safe identifier for tags."""
        return "".join(c.lower() if c.isalnum() else "-" for c in self.name).strip("-")


def load_shows() -> list[ShowConfig]:
    """Load configured shows from config/shows.yaml."""
    path = CONFIG_DIR / "shows.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    shows = []
    for entry in data.get("shows", []):
        sources = entry.get("sources", {})
        shows.append(ShowConfig(
            name=entry["name"],
            profile=entry.get("profile", "hybrid"),
            rss=sources.get("rss"),
            youtube_channel=sources.get("youtube_channel"),
            speakers_hint=entry.get("speakers_hint", ""),
            active=entry.get("active", True),
        ))
    return shows


def find_show_by_url(url: str) -> Optional[ShowConfig]:
    """Best-effort match of a URL to a configured show (for manual mode)."""
    shows = load_shows()
    url_lower = url.lower()
    for show in shows:
        if show.youtube_channel and show.youtube_channel.lower() in url_lower:
            return show
        if show.rss and show.rss.lower().split("/")[2] in url_lower:
            return show
    return None


def load_prompt(profile: str) -> str:
    """Load the synthesis prompt for a profile."""
    path = PROMPTS_DIR / f"{profile}.md"
    if not path.exists():
        path = PROMPTS_DIR / "hybrid.md"
    return path.read_text()


def load_trusted_domains() -> list[str]:
    """Load whitelist for political research."""
    path = CONFIG_DIR / "trusted_sources.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    return data.get("domains", [])


# ─── API key checks ──────────────────────────────────────────────────────────

def require_env(*keys: str):
    """Raise a clear error if any required env var is missing."""
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Add them to your .env file (see .env.example)."
        )


def check_config() -> dict:
    """
    Return a structured dict describing env key status, token validity,
    and configured shows. Used by both the CLI cmd_check and the MCP check_config tool.
    """
    from delivery import deliver

    key_specs = {
        "DEEPGRAM_API_KEY": "Transcription (required)",
        "ANTHROPIC_API_KEY": "LLM (required)",
        "READWISE_TOKEN": "Reader delivery (required)",
        "BRAVE_API_KEY": "News search (optional, current_events/hybrid)",
        "GOOGLE_BOOKS_API_KEY": "Books (optional)",
    }

    keys_status = {}
    for key, desc in key_specs.items():
        keys_status[key] = {"set": bool(os.getenv(key)), "description": desc}

    readwise_valid = None
    if os.getenv("READWISE_TOKEN"):
        readwise_valid = deliver.verify_token()

    shows = load_shows()
    shows_info = []
    for s in shows:
        sources = []
        if s.rss:
            sources.append("RSS")
        if s.youtube_channel:
            sources.append("YouTube")
        shows_info.append({
            "name": s.name,
            "profile": s.profile,
            "sources": sources,
            "active": s.active,
        })

    return {
        "keys": keys_status,
        "readwise_token_valid": readwise_valid,
        "shows": shows_info,
    }
