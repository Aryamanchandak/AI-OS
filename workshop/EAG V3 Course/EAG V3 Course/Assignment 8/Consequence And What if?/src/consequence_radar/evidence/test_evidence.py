from consequence_radar.evidence import verify_claims
from consequence_radar.models import EvidenceClaimDraft, SourceRecord


def test_exact_passage_verification_rejects_paraphrase():
    source = SourceRecord(id="S1", url="https://example.com", title="Source", publisher="example.com", extracted_text="Revenue increased by 12 percent in the quarter.")
    drafts = [
        EvidenceClaimDraft(source_id="S1", claim="Revenue rose", exact_passage="Revenue   increased by 12 percent in the quarter.", claim_type="fact", stance="supports"),
        EvidenceClaimDraft(source_id="S1", claim="Revenue surged", exact_passage="Revenue surged strongly", claim_type="fact", stance="supports"),
    ]
    accepted, rejected = verify_claims(drafts, [source])
    assert len(accepted) == len(rejected) == 1 and accepted[0].passage_verified
