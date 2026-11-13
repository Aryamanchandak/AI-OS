"""Configuration. Everything secret comes from .env, which is gitignored."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # -- core ---------------------------------------------------------------
    db_path: Path = ROOT / "data" / "switchboard.db"
    home_timezone: str = "Asia/Kolkata"

    anthropic_api_key: str = ""
    triage_model: str = "claude-sonnet-5"   # cheap, runs on every message
    draft_model: str = "claude-opus-5"      # quality, runs only on survivors

    # -- notification policy (DESIGN.md 2.11) -------------------------------
    quiet_hours_start: int = 22
    quiet_hours_end: int = 8
    urgent_breaks_quiet_hours: bool = True

    # -- cost guards (DESIGN.md 2.15c) --------------------------------------
    max_documents_per_day: int = 5
    heartbeat_stale_minutes: int = 15

    # -- Telegram: TWO bots. See DESIGN.md 2.1b -----------------------------
    # Control bot sends approval prompts. Its chat is excluded from ingestion.
    telegram_control_bot_token: str = ""
    telegram_control_chat_id: str = ""
    telegram_inbox_bot_token: str = ""

    # -- Gmail --------------------------------------------------------------
    gmail_credentials_path: Path = ROOT / "credentials.json"
    gmail_token_path: Path = ROOT / "token.json"

    # -- Slack (user token for DM coverage, not bot scopes — DESIGN.md 2.1c)
    slack_user_token: str = ""
    slack_app_token: str = ""

    # -- Twilio -------------------------------------------------------------
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_number: str = ""
    twilio_poll_mode: bool = True   # no public URL needed; webhook is opt-in

    # -- WhatsApp (Phase 6) -------------------------------------------------
    whatsapp_enabled: bool = False
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""   # verifies X-Hub-Signature-256


settings = Settings()
