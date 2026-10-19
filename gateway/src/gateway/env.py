"""Load API keys from gateway/.env into the process environment. The only python-dotenv import."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_env() -> None:
    """Read ENV_FILE if it exists; variables already set in the shell win."""
    load_dotenv(ENV_FILE, override=False)
