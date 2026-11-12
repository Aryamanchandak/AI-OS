from __future__ import annotations

import re

from pydantic import ValidationError

from ..models import EvidenceClaim, EvidenceClaimDraft, RejectedClaim, SourceRecord


def normalize_passage(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def verify_claims(drafts: list[EvidenceClaimDraft], sources: list[SourceRecord], start: int = 1) -> tuple[list[EvidenceClaim], list[RejectedClaim]]:
    source_map = {s.id: s for s in sources}
    accepted, rejected = [], []
    for draft in drafts:
        source = source_map.get(draft.source_id)
        passage = normalize_passage(draft.exact_passage)
        if source is None:
            rejected.append(RejectedClaim(claim=draft.claim, source_id=draft.source_id, exact_passage=draft.exact_passage, reason="unknown source")); continue
        if not passage or passage not in normalize_passage(source.extracted_text):
            rejected.append(RejectedClaim(claim=draft.claim, source_id=draft.source_id, exact_passage=draft.exact_passage, reason="exact passage not found")); continue
        # EvidenceClaim tightens the draft's ``claim`` to a non-empty string.
        # A blank one used to raise out of verification and fail the whole run;
        # an unusable claim belongs on the rejected ledger like any other.
        try:
            accepted.append(EvidenceClaim(id=f"C{start + len(accepted)}", passage_verified=True, **draft.model_dump()))
        except ValidationError as exc:
            rejected.append(RejectedClaim(claim=draft.claim, source_id=draft.source_id, exact_passage=draft.exact_passage, reason=f"claim failed validation: {exc.errors()[0]['msg']}"))
    return accepted, rejected

