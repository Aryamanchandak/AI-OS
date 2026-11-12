"""Publication adapters that place approved intake results into the vault."""

from gateway.ingestion.publish.vault_writer import (
    approved_intake_result,
    finalize_published_page,
    ApprovalRequiredError,
    publish_approved_page,
    write_note_to_vault,
)

__all__ = [
    "ApprovalRequiredError",
    "publish_approved_page",
    "approved_intake_result",
    "finalize_published_page",
    "write_note_to_vault",
]
