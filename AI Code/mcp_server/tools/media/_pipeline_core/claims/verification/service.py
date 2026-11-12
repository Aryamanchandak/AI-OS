"""Generic claim verification boundary."""

from tools.media._pipeline_core.shared.contracts import ClaimVerificationBatch, ClaimVerificationRequest


class ClaimVerificationService:
    """Verify structured claims independent of transport or orchestration layer."""

    def verify(self, request: ClaimVerificationRequest) -> ClaimVerificationBatch:
        # Expected contract:
        # - Input is a ClaimVerificationRequest containing a list of ClaimRecord items.
        # - Output must be a ClaimVerificationBatch containing one
        #   ClaimVerificationRecord per input claim.
        #
        # Implementation notes for the future concrete adapter:
        # - Verify each claim independently against external web sources.
        # - Use research_tools/sources/gemini_web.py as the primary grounded-search
        #   verifier when the research_tools integration is available.
        # - Populate each ClaimVerificationRecord with a verdict
        #   (true/false/mixed/unverifiable/pending), rationale, confidence level,
        #   and supporting_sources containing URL + excerpt evidence.
        # - Future integration will likely live in the research_tools project and is
        #   out of scope for this scaffold pass.
        raise NotImplementedError(
            "Provide a generic verification implementation for arbitrary claims."
        )
