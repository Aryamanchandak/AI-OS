"""Component 8: human-controlled abbreviation and spelling cleanup.

Public surface consumed by ``CleanupGate``: :mod:`working` for the ephemeral
per-item state machine, :mod:`store` for the mapping repository and audit
log, :mod:`abbreviations` and :mod:`spelling` for candidate discovery.
"""

from ingestion.text_cleanup.models import Candidate, Passage
from ingestion.text_cleanup.working import WorkingState

__all__ = ["Candidate", "Passage", "WorkingState"]
