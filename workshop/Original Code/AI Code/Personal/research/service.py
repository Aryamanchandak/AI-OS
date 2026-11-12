"""Placeholder client for separated research integration."""

from mcp_tools.claims.contracts import ClaimVerificationBatch, ClaimVerificationRequest

from .contracts import ResearchBatchResult, ResearchClaimInput, build_research_inputs


class ExternalResearchClient:
    """Research-backed verification adapter for the generic claims domain."""

    def verify_claims(self, claims: list[ResearchClaimInput]) -> ResearchBatchResult:
        raise NotImplementedError(
            "Research and verification should be provided by an external service. "
            "Only the adapter contract is kept in this repository."
        )

    def verify(self, request: ClaimVerificationRequest) -> ClaimVerificationBatch:
        result = self.verify_claims(build_research_inputs(request))
        return result.to_verification_batch()
