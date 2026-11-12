import type { KnowledgeEnvelopePayload, KnowledgeProposalPayload } from "../api/client";

/**
 * `proposal` is `dict[str, Any]` on the wire because its shape genuinely
 * differs by `proposal_type` (models.py:121-190). These are the three shapes,
 * narrowed here rather than upstream, the same way ImageReview.tsx narrows its
 * localStorage draft: a boolean type-guard function per shape, never a blind
 * cast.
 */
export type EvidenceRef = {
  source_record_id: string;
  quote: string;
  normalized_char_start: number | null;
  normalized_char_end: number | null;
};

export type ConceptProposalView = {
  proposal_id: string;
  label: string;
  aliases: string[];
  model_confidence: number;
  status: "proposed" | "approved" | "rejected";
  source_record_id: string;
  evidence: EvidenceRef[];
  domain: string | null;
};

export type ClaimProposalView = {
  proposal_id: string;
  text: string;
  concept_labels: string[];
  model_confidence: number;
  status: "current" | "superseded" | "disputed" | "proposed" | "retracted";
  source_record_id: string;
  evidence: EvidenceRef[];
  observed_at: string | null;
  valid_from: string | null;
  valid_to: string | null;
};

export type RelationProposalView = {
  proposal_id: string;
  subject: string;
  predicate: string;
  object: string;
  model_confidence: number;
  status: "proposed" | "approved" | "rejected";
  source_record_id: string;
  evidence: EvidenceRef[];
  domain: string | null;
  hierarchical: boolean;
};

/** `payload.proposal_type` is a trusted server value — this only guards the
 * nested object actually matching the shape that discriminant promises. */
function isEvidenceList(value: unknown): value is EvidenceRef[] {
  return Array.isArray(value) && value.every((item) => (
    typeof item === "object"
    && item !== null
    && typeof (item as EvidenceRef).source_record_id === "string"
    && typeof (item as EvidenceRef).quote === "string"
  ));
}

function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function isConceptProposalView(
  value: Record<string, unknown>,
): value is ConceptProposalView {
  return (
    typeof value.proposal_id === "string"
    && typeof value.label === "string"
    && isStringList(value.aliases)
    && typeof value.model_confidence === "number"
    && typeof value.status === "string"
    && typeof value.source_record_id === "string"
    && isEvidenceList(value.evidence)
  );
}

export function isClaimProposalView(
  value: Record<string, unknown>,
): value is ClaimProposalView {
  return (
    typeof value.proposal_id === "string"
    && typeof value.text === "string"
    && isStringList(value.concept_labels)
    && typeof value.model_confidence === "number"
    && typeof value.status === "string"
    && typeof value.source_record_id === "string"
    && isEvidenceList(value.evidence)
  );
}

export function isRelationProposalView(
  value: Record<string, unknown>,
): value is RelationProposalView {
  return (
    typeof value.proposal_id === "string"
    && typeof value.subject === "string"
    && typeof value.predicate === "string"
    && typeof value.object === "string"
    && typeof value.model_confidence === "number"
    && typeof value.status === "string"
    && typeof value.source_record_id === "string"
    && isEvidenceList(value.evidence)
    && typeof value.hierarchical === "boolean"
  );
}

/**
 * Both `KnowledgeEnvelopePayload` and `KnowledgeProposalPayload` carry
 * `& { [key: string]: unknown }` (PayloadBody's `extra="allow"`), so an
 * inline `payload.envelope_level === true` check does not reliably narrow the
 * union — TypeScript sees `unknown` on the other member through the index
 * signature. An explicit predicate sidesteps that: its `is` return type is
 * trusted at the call site regardless.
 */
export function isKnowledgeEnvelopePayload(
  payload: KnowledgeEnvelopePayload | KnowledgeProposalPayload,
): payload is KnowledgeEnvelopePayload {
  return payload.envelope_level === true;
}

/**
 * Plain-language sentence for each of the 13 fixed codes `assess_review`
 * (review_policy.py) and pipeline.py:466,476 emit. The literal code is always
 * shown alongside this, never hidden. A code missing from this table (free
 * text from `model_review_reasons`, or an unknown future code) renders as its
 * literal string with no sentence — there is no fixed string to write for it.
 */
export const REVIEW_SIGNAL_COPY: Record<string, string> = {
  empty_semantic_extraction:
    "The model didn't extract any concepts, claims, or relations from this highlight.",
  overall_model_confidence_below_threshold:
    "The model's overall confidence in this extraction fell below the review threshold.",
  source_quality_signal:
    "The model flagged a quality issue with the source text itself.",
  source_is_page_scanner:
    "This came from a photographed page, so the text was OCR'd rather than typed.",
  cleanup_suggestion_pending:
    "Spelling or abbreviation cleanup was suggested for this text and has not been resolved yet.",
  missing_evidence:
    "This proposal has no supporting evidence quoted from the source text.",
  evidence_source_mismatch:
    "The evidence quoted for this proposal points to a different source than the one being reviewed.",
  evidence_offsets_missing:
    "The evidence quote has no recorded location in the source text.",
  evidence_range_invalid:
    "The evidence quote's recorded location doesn't fall within the source text.",
  evidence_quote_mismatch:
    "The evidence quote doesn't match the text at its recorded location in the source.",
  evidence_quote_ambiguous:
    "The evidence quote appears more than once in the source text, so its exact location is ambiguous.",
  proposal_model_confidence_below_threshold:
    "The model's confidence in this specific proposal fell below the review threshold.",
  alias_or_identity_proposal:
    "This proposal identifies two things as the same — a concept with an alias, or a relation like "
    + "same-as/equivalent-to — and identity merges always require human review.",
};
