"""Generic claim extraction boundary."""

from tools.media._pipeline_core.shared.contracts import ClaimExtractionBatch, ClaimExtractionRequest


class ClaimExtractionService:
    """Extract structured claims from arbitrary source content."""

    def extract(self, request: ClaimExtractionRequest) -> ClaimExtractionBatch:
        # Expected contract:
        # - Input arrives as a ContentInput embedded in ClaimExtractionRequest.
        # - ContentInput carries transcript text or other source text, a source_ref, and metadata.
        # - Output must be a ClaimExtractionBatch containing structured ClaimRecord items.
        #
        # Implementation notes for the future concrete adapter:
        # - Call an LLM with a structured prompt that identifies factual claims in the content.
        # - Ask the model to attribute claims to speakers where possible.
        # - Ask the model to classify each claim type, for example statistical claim,
        #   attribution claim, prediction, or similar factual categories.
        # - Generate a stable claim_id for each ClaimRecord, such as a UUID or a hash
        #   derived from quote + source_ref.
        # - Pass request.max_claims and request.claim_types through as explicit prompt
        #   constraints so extraction behavior is controllable by callers.
        # - Future integration target is LLM_Gateway once that interface is available.
        # - This service remains intentionally unimplemented in the current scope.
        raise NotImplementedError(
            "Provide a generic extraction implementation that accepts any content input."
        )
