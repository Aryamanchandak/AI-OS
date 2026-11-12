"""Backward-compatible re-exports for claims-domain contracts."""

from tools.media._pipeline_core.shared.contracts import (
    ClaimExtractionBatch,
    ClaimExtractionRequest,
    ClaimRecord,
    ClaimVerificationBatch,
    ClaimVerificationRecord,
    ClaimVerificationRequest,
    ContentInput,
    VerificationSource,
)

__all__ = [
    "ClaimExtractionBatch",
    "ClaimExtractionRequest",
    "ClaimRecord",
    "ClaimVerificationBatch",
    "ClaimVerificationRecord",
    "ClaimVerificationRequest",
    "ContentInput",
    "VerificationSource",
]
