from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'consequence_radar.db'}"
    web_host: str = "127.0.0.1"
    web_port: int = Field(8010, ge=1024, le=65535)
    gemini_api_key: str | None = None
    google_api_key: str | None = None
    fast_model: str = "gemini-2.5-flash"
    reasoning_model: str = "gemini-2.5-pro"
    report_model: str = "gemini-2.5-pro"
    max_research_cycles: int = Field(3, ge=1, le=10)
    max_graph_nodes: int = Field(24, ge=3, le=100)
    max_graph_edges: int = Field(36, ge=2, le=200)
    max_research_tasks_per_cycle: int = Field(8, ge=1, le=30)
    max_search_queries_per_run: int = Field(30, ge=1, le=200)
    # Adds the url_context tool alongside google_search in grounded search
    # calls so per-result relevance descriptions can populate SearchResult
    # snippets. Disable if it proves unreliable or expensive.
    enable_url_context_search: bool = True
    max_fetched_sources_per_run: int = Field(50, ge=1, le=200)
    # A full run issues ~20 generations: selection, initial graph, three
    # research cycles of up to four each, quantification, review, challenge,
    # adjudication, case selection and the report -- plus room for a parse
    # retry.  Grounded search draws on max_search_queries_per_run instead.
    max_model_calls_per_run: int = Field(45, ge=1, le=100)
    max_wall_time_seconds: int = Field(1800, ge=10, le=7200)
    max_output_tokens: int = Field(32_768, ge=1024, le=65_536)
    report_context_token_budget: int = Field(24000, ge=1000)
    report_min_words: int = Field(800, ge=100)
    report_max_words: int = Field(1200, ge=200)
    worker_count: int = Field(2, ge=1, le=8)
    fetch_timeout_seconds: float = Field(12.0, ge=1, le=60)
    fetch_max_bytes: int = Field(1_500_000, ge=10_000, le=10_000_000)
    fetch_redirect_limit: int = Field(4, ge=0, le=10)
    fetch_retry_limit: int = Field(1, ge=0, le=3)

    @model_validator(mode="after")
    def coherent_report_bounds(self):
        # Each bound is individually plausible, so an inverted pair passed
        # startup and then failed every report at the last stage with a word
        # count that no article could satisfy. Reject it at configuration time.
        if self.report_min_words > self.report_max_words:
            raise ValueError("REPORT_MIN_WORDS must not exceed REPORT_MAX_WORDS")
        return self

    @property
    def api_key(self) -> str | None:
        return self.gemini_api_key or self.google_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
