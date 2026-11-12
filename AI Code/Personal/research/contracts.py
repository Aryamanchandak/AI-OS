"""Contracts for a research-backed claim verification adapter."""

from __future__ import annotations

from pydantic import BaseModel, Field

from mcp_tools.claims.contracts import (
    ClaimRecord,
    ClaimVerificationBatch,
    ClaimVerificationRecord,
    ClaimVerificationRequest,
    VerificationSource,
)


class ResearchClaimInput(BaseModel):
    claim: ClaimRecord
    search_query: str = ""


class ResearchClaimResult(BaseModel):
    claim_id: str
    status: str = "pending"
    rationale: str = ""
    sources: list[VerificationSource] = Field(default_factory=list)


class ResearchBatchResult(BaseModel):
    run_id: str = ""
    items: list[ResearchClaimResult] = Field(default_factory=list)

    def to_verification_batch(self) -> ClaimVerificationBatch:
        return ClaimVerificationBatch(
            run_id=self.run_id,
            items=[
                ClaimVerificationRecord(
                    claim_id=item.claim_id,
                    verdict=item.status,
                    rationale=item.rationale,
                    supporting_sources=item.sources,
                )
                for item in self.items
            ],
        )


def build_research_inputs(
    request: ClaimVerificationRequest,
) -> list[ResearchClaimInput]:
    return [ResearchClaimInput(claim=claim) for claim in request.claims]
