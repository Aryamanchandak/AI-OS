from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv


def ai_code_root(start: Path | None = None) -> Path | None:
    """Return the enclosing ``AI Code`` directory when one is discoverable."""
    cursor = (start or Path.cwd()).resolve()
    for parent in (cursor, *cursor.parents):
        if parent.name == "AI Code":
            return parent
    return None


def load_root_env(start: Path | None = None) -> Path | None:
    """Load the shared ``AI Code/.env`` without overriding process env vars.

    Production ingestion is allowed to read this one shared secrets file. A
    deployment outside the monorepo may supply variables through the process
    environment instead, so a missing discoverable root is not itself fatal.
    """
    root = ai_code_root(start)
    if root is None:
        return None
    env_path = root / ".env"
    if not env_path.is_file():
        return None
    load_dotenv(env_path, override=False)
    return env_path


def central_database_root(start: Path | None = None) -> Path:
    override = os.environ.get("INGESTION_DATABASE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    root = ai_code_root(start)
    if root is not None:
        return root / "Database"
    raise RuntimeError(
        "Cannot resolve the central Database root; set INGESTION_DATABASE_ROOT"
    )


@dataclass(frozen=True)
class SegmentationConfig:
    """The complete ingestion-owned semantic segmentation policy."""

    mode: Literal["gateway", "deterministic"] = "gateway"
    passthrough_max_words: int = 40
    chat_profile: str = "document-segmentation-v1"
    required_provider: str = "phi4-local"
    required_model: str = "phi4:14b-q4_K_M"
    inspection_target_words: int = 500
    # Phi-4's published context is 16K tokens. Keep 4K tokens in reserve for
    # the prompt, structured response, and conservative token estimation.
    max_input_tokens: int = 12_000
    max_output_tokens: int = 256
    context_sentences_before: int = 3
    context_sentences_after: int = 3
    max_attempts: int = 1
    failure_policy: Literal["pending"] = "pending"

    def validate(self) -> None:
        if self.passthrough_max_words < 0:
            raise ValueError("passthrough_max_words must be non-negative")
        if not self.chat_profile.strip():
            raise ValueError("chat_profile cannot be blank")
        if not self.required_provider.strip() or not self.required_model.strip():
            raise ValueError("required segmentation provider/model cannot be blank")
        if self.inspection_target_words < 1:
            raise ValueError("inspection_target_words must be positive")
        if self.max_input_tokens < 1 or self.max_output_tokens < 1:
            raise ValueError("segmentation token budgets must be positive")
        if (
            self.context_sentences_before < 0
            or self.context_sentences_after < 0
        ):
            raise ValueError("segmentation context sizes cannot be negative")
        if self.max_attempts != 1:
            raise ValueError("segmentation max_attempts must be 1 (fail-fast)")
        if self.mode == "gateway" and self.failure_policy != "pending":
            raise ValueError("gateway segmentation failures must remain pending")

    def report(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EmbeddingChunkConfig:
    """Sentence-aware vector policy, independent of highlight storage."""

    target_sentences: int = 3
    minimum_sentences: int = 2
    max_words: int = 150
    max_characters: int = 8_000
    sentence_overlap: int = 1

    def validate(self) -> None:
        if self.target_sentences < 1:
            raise ValueError("target_sentences must be positive")
        if self.minimum_sentences < 1:
            raise ValueError("minimum_sentences must be positive")
        if self.minimum_sentences > self.target_sentences:
            raise ValueError("minimum_sentences cannot exceed target_sentences")
        if self.max_words < 1 or self.max_characters < 1:
            raise ValueError("embedding chunk ceilings must be positive")
        if self.max_characters > 8_000:
            raise ValueError(
                "max_characters cannot exceed the gateway's 8000-character limit"
            )
        if self.sentence_overlap < 0:
            raise ValueError("sentence_overlap cannot be negative")
        if self.sentence_overlap >= self.target_sentences:
            raise ValueError("sentence_overlap must be smaller than target_sentences")


@dataclass(frozen=True)
class IntakeConfig:
    """Configuration for the repository's shared intake front door."""

    drop_folder: Path = Path("/Users/aryamanchandak/Desktop/AI OS INGESTION")
    vault_path: Path | None = None
    post_publish_root: Path | None = None
    cleanup_provider: str = "gemma"
    # Component 8's human spelling review. Deliberately a separate key from
    # cleanup_provider: that one already configures the unrelated automatic
    # OCR-repair model (sources/page_scanner/cleanup.py), which runs earlier
    # and is untouched by Component 8 (C8-C9) -- changing one must never
    # silently change the other.
    spelling_review_provider: str = "gemma"

    def validate(self) -> None:
        if not str(self.drop_folder).strip():
            raise ValueError("drop_folder cannot be blank")
        if not self.cleanup_provider.strip():
            raise ValueError("cleanup_provider cannot be blank")
        if self.cleanup_provider not in {"gemma", "phi4-local"}:
            raise ValueError("cleanup_provider must name a configured local provider")
        if not self.spelling_review_provider.strip():
            raise ValueError("spelling_review_provider cannot be blank")
        if self.spelling_review_provider not in {"gemma", "phi4-local"}:
            raise ValueError(
                "spelling_review_provider must name a configured local provider"
            )
        if self.post_publish_root is not None:
            drop = self.drop_folder.expanduser().resolve()
            destination = self.post_publish_root.expanduser().resolve()
            if destination == drop or destination.is_relative_to(drop):
                raise ValueError("post_publish_root must be outside drop_folder")


@dataclass(frozen=True)
class IngestionConfig:
    database_root: Path
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    embedding_chunks: EmbeddingChunkConfig = field(default_factory=EmbeddingChunkConfig)
    extraction_version: str = "semantic_extraction_v1"
    review_confidence_threshold: float = 0.75
    # How many highlights share one extraction call. Extraction is the only
    # paid model call in the pipeline, so this is the cost dial: a run needs
    # ceil(pending_highlights / batch_size) calls, not one per highlight. Kept
    # small because a highlight can be ~512 words and the whole batch dies
    # together if the response outgrows the output budget (see
    # `extraction.gateway.DEFAULT_BATCH_MAX_TOKENS`). Raise it only alongside
    # measured output-token usage.
    extraction_batch_size: int = 4
    intake: IntakeConfig | None = None

    @classmethod
    def default(cls) -> "IngestionConfig":
        return cls(database_root=central_database_root())

    @property
    def raw_root(self) -> Path:
        return self.database_root / "raw"

    @property
    def ledger_path(self) -> Path:
        return self.database_root / "sqlite" / "ingestion.db"

    @property
    def content_db_path(self) -> Path:
        return self.database_root / "sqlite" / "content.db"

    @property
    def chroma_path(self) -> Path:
        return self.database_root / "chroma"

    @property
    def envelope_root(self) -> Path:
        return self.database_root / "envelopes"

    @property
    def neo4j_path(self) -> Path:
        return self.database_root / "neo4j"

    @property
    def coordinator_db_path(self) -> Path:
        return self.database_root / "sqlite" / "coordinator.db"

    @property
    def page_scanner_db_path(self) -> Path:
        return self.database_root / "sqlite" / "processed.db"

    @property
    def text_cleanup_db_path(self) -> Path:
        return self.database_root / "sqlite" / "text_cleanup.db"

    def validate(self) -> None:
        self.segmentation.validate()
        self.embedding_chunks.validate()
        if self.intake is not None:
            self.intake.validate()
        if not 0.0 <= self.review_confidence_threshold <= 1.0:
            raise ValueError("review_confidence_threshold must be between 0 and 1")
        if self.extraction_batch_size < 1:
            raise ValueError("extraction_batch_size must be at least 1")
