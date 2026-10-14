import { AlertTriangle, Check, Layers, Pencil, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type {
  KnowledgeEnvelopePayload,
  KnowledgeProposalPayload,
  KnowledgeProposalPending,
  PhotoPassage,
  ReviewSignalBody,
  SiblingProposal,
} from "../api/client";
import { ActionBar, type ActionDescriptor, type UnsupportedActions } from "../components/ActionBar";
import { AdapterFrame, Metric } from "../components/primitives";
import { PhotoStage, type PhotoBox } from "../components/PhotoStage";
import { useEvidenceImage } from "../hooks/useEvidenceImage";
import {
  isClaimProposalView,
  isConceptProposalView,
  isKnowledgeEnvelopePayload,
  isRelationProposalView,
  REVIEW_SIGNAL_COPY,
  type ClaimProposalView,
  type ConceptProposalView,
  type EvidenceRef,
  type RelationProposalView,
} from "./knowledgeProposal";
import type { AdapterProps, SubmitDecision } from "./types";

function confidenceLabel(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "Unknown";
  return typeof value === "number" ? `${Math.round(value * 100)}%` : value;
}

function splitList(value: string): string[] {
  return value.split(",").map((entry) => entry.trim()).filter((entry) => entry.length > 0);
}

function SignalList({ signals }: { signals: ReviewSignalBody[] }) {
  if (signals.length === 0) return <p className="diag-empty">No review signals.</p>;
  return (
    <ul className="signal-list">
      {signals.map((signal, index) => {
        const copy = REVIEW_SIGNAL_COPY[signal.code];
        const detail = signal.detail;
        const hasDetail = detail !== undefined && detail !== null && detail !== "";
        return (
          <li className="signal-row" key={`${signal.code}-${signal.proposal_id ?? "envelope"}-${index}`}>
            <code>{signal.code}</code>
            {copy && <p>{copy}</p>}
            {hasDetail && (
              <p className="signal-detail">
                {typeof detail === "object" ? JSON.stringify(detail) : String(detail)}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function EvidenceList({ evidence }: { evidence: EvidenceRef[] }) {
  if (evidence.length === 0) return <p className="diag-empty">No evidence recorded.</p>;
  return (
    <ul className="evidence-list">
      {evidence.map((item, index) => (
        <li key={index}>
          <blockquote>{item.quote}</blockquote>
          <p className="eyebrow">
            {item.normalized_char_start ?? "?"}–{item.normalized_char_end ?? "?"}
          </p>
        </li>
      ))}
    </ul>
  );
}

/**
 * Marks the exact evidence span in `highlight_text` by offset, never by
 * re-searching for the quote. The offsets come from the source record's
 * normalized content, a different string than `highlight_text` — the backend
 * emits evidence_offsets_missing / evidence_range_invalid /
 * evidence_quote_mismatch precisely because they can disagree. A mark is only
 * ever drawn when the slice it names actually equals the quote; otherwise the
 * text renders plainly rather than showing a confidently-wrong mark.
 */
function HighlightWithEvidence({
  text,
  quote,
  start,
  end,
}: {
  text: string | null;
  quote: string | null;
  start: number | null;
  end: number | null;
}) {
  if (!text) return <p className="diag-empty">No highlight text recorded.</p>;
  if (
    quote === null || start === null || end === null
    || start < 0 || end <= start || end > text.length
    || text.slice(start, end) !== quote
  ) {
    return <p className="highlight-text">{text}</p>;
  }
  return (
    <p className="highlight-text">
      {text.slice(0, start)}
      <mark>{text.slice(start, end)}</mark>
      {text.slice(end)}
    </p>
  );
}

/**
 * The photographed source page behind a highlight, when there is one --
 * absent for the common case (a typed vault note has no photo). Every
 * passage on the page is boxed, not just the one behind this proposal's
 * evidence quote: the pipeline doesn't track that level of provenance, so a
 * reviewer locates their highlight visually among the page's OCR'd passages,
 * the same way ImageReview.tsx already lets them check OCR against a photo
 * instead of taking the extraction on faith.
 */
function ProposalPhotoPanel({
  payload,
  token,
  runId,
  itemId,
}: {
  payload: KnowledgeProposalPayload;
  token: string;
  runId: string;
  itemId: string;
}) {
  const { imageUrl, imageError } = useEvidenceImage(token, runId, itemId);
  const boxes = useMemo<PhotoBox[]>(
    () => (payload.photo_passages ?? [])
      .filter((passage): passage is PhotoPassage & { bbox: number[] } => passage.bbox !== null && passage.bbox !== undefined)
      .map((passage, index) => ({
        key: String(index),
        bbox: passage.bbox as [number, number, number, number],
        title: passage.ocr_text || undefined,
      })),
    [payload.photo_passages],
  );

  return (
    <section className="proposal-photo" aria-label="Source page">
      <p className="eyebrow">
        Source page{payload.photo_page_number != null ? ` · page ${payload.photo_page_number}` : ""}
      </p>
      <PhotoStage
        imageUrl={imageUrl}
        imageError={imageError}
        boxes={boxes}
        alt="Photographed source page"
        label="Source page"
      />
    </section>
  );
}

/**
 * Every proposal derived from the same highlight, so a reviewer sees the
 * whole envelope at a glance instead of discovering "one more" only after
 * deciding the one in front of them. Read-only: deciding a listed sibling
 * still happens on its own turn, once the coordinator surfaces it as the
 * active proposal below.
 */
function ProposalRoadmap({
  current,
  siblings,
}: {
  current: { proposal_id: string; proposal_type: string };
  siblings: SiblingProposal[];
}) {
  if (siblings.length === 0) return null;
  const all = [
    { ...current, status: "active", summary: null as string | null },
    ...siblings,
  ];
  return (
    <section aria-label="Other proposals from this highlight">
      <p className="eyebrow">This highlight ({all.length} proposals)</p>
      <ul className="roadmap-list">
        {all.map((entry) => (
          <li
            key={entry.proposal_id}
            className={`roadmap-row roadmap-${entry.status}`}
            aria-current={entry.proposal_id === current.proposal_id ? "step" : undefined}
          >
            <code>{entry.proposal_type}</code>
            <span className="roadmap-summary">
              {entry.proposal_id === current.proposal_id ? "Reviewing now" : entry.summary}
            </span>
            <span className="roadmap-status">{entry.status}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

type ProposalScaffold = {
  pending: KnowledgeProposalPending;
  payload: KnowledgeProposalPayload;
  busy: boolean;
  submit: SubmitDecision;
  onUnsupported: (unsupported: UnsupportedActions | null) => void;
};

/** Shared chrome around every proposal-level card: identity, source, highlight
 * context, confidences and signals — every field a reviewer needs regardless
 * of proposal_type, none of it editable. */
function ProposalContext({ payload }: { payload: KnowledgeProposalPayload }) {
  return (
    <>
      <div className="field-rows">
        <div className="metric"><span>Source note</span><strong>{payload.source_note_path ?? "Unknown"}</strong></div>
        <div className="metric"><span>Origin</span><strong>{payload.origin_kind ?? "Unknown"}</strong></div>
        <div className="metric"><span>Highlight index</span><strong>{payload.highlight_index ?? "Unknown"}</strong></div>
      </div>
      <HighlightWithEvidence
        text={payload.highlight_text ?? null}
        quote={payload.evidence_quote ?? null}
        start={payload.evidence_start_char ?? null}
        end={payload.evidence_end_char ?? null}
      />
      <section>
        <p className="eyebrow">Review signals</p>
        <SignalList signals={payload.signals} />
      </section>
    </>
  );
}

function ConceptReview({ pending, payload, view, busy, submit, onUnsupported }: ProposalScaffold & { view: ConceptProposalView }) {
  const [label, setLabel] = useState(view.label);
  const [aliasesText, setAliasesText] = useState(view.aliases.join(", "));

  const descriptors = useMemo<ActionDescriptor[]>(() => [
    { action: "approve", label: <>Approve <Check size={17} /></>, tone: "primary", buildPayload: () => ({}) },
    {
      action: "edit",
      label: <>Save edit <Pencil size={16} /></>,
      tone: "primary",
      disabled: !label.trim(),
      buildPayload: () => ({
        edited_proposal: { ...payload.proposal, label: label.trim(), aliases: splitList(aliasesText) },
      }),
    },
    { action: "reject", label: "Reject", tone: "danger", buildPayload: () => ({}) },
  ], [aliasesText, label, payload.proposal]);

  return (
    <div className="proposal-card">
      <div className="field-rows">
        <div className="metric"><span>Proposal type</span><strong>Concept</strong></div>
        <div className="metric"><span>Proposal confidence</span><strong>{confidenceLabel(payload.proposal_confidence)}</strong></div>
        <div className="metric"><span>Proposal id</span><strong>{view.proposal_id}</strong></div>
        <div className="metric"><span>Model confidence</span><strong>{confidenceLabel(view.model_confidence)}</strong></div>
        <div className="metric"><span>Status</span><strong>{view.status}</strong></div>
        <div className="metric"><span>Source record</span><strong>{view.source_record_id}</strong></div>
        <div className="metric"><span>Domain</span><strong>{view.domain ?? "Not tagged"}</strong></div>
      </div>
      <div className="edit-grid">
        <label>
          Label
          <input value={label} onChange={(event) => setLabel(event.target.value)} />
        </label>
        <label>
          Aliases (comma-separated)
          <input value={aliasesText} onChange={(event) => setAliasesText(event.target.value)} />
        </label>
      </div>
      <p className="eyebrow">Evidence</p>
      <EvidenceList evidence={view.evidence} />
      <ActionBar
        adapter="knowledge_proposal"
        allowedActions={pending.allowed_actions}
        descriptors={descriptors}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    </div>
  );
}

function ClaimReview({ pending, payload, view, busy, submit, onUnsupported }: ProposalScaffold & { view: ClaimProposalView }) {
  const [text, setText] = useState(view.text);
  const [conceptLabelsText, setConceptLabelsText] = useState(view.concept_labels.join(", "));

  const descriptors = useMemo<ActionDescriptor[]>(() => [
    { action: "approve", label: <>Approve <Check size={17} /></>, tone: "primary", buildPayload: () => ({}) },
    {
      action: "edit",
      label: <>Save edit <Pencil size={16} /></>,
      tone: "primary",
      disabled: !text.trim(),
      buildPayload: () => ({
        edited_proposal: {
          ...payload.proposal,
          text: text.trim(),
          concept_labels: splitList(conceptLabelsText),
        },
      }),
    },
    { action: "reject", label: "Reject", tone: "danger", buildPayload: () => ({}) },
  ], [conceptLabelsText, payload.proposal, text]);

  return (
    <div className="proposal-card">
      <div className="field-rows">
        <div className="metric"><span>Proposal type</span><strong>Claim</strong></div>
        <div className="metric"><span>Proposal confidence</span><strong>{confidenceLabel(payload.proposal_confidence)}</strong></div>
        <div className="metric"><span>Proposal id</span><strong>{view.proposal_id}</strong></div>
        <div className="metric"><span>Model confidence</span><strong>{confidenceLabel(view.model_confidence)}</strong></div>
        <div className="metric"><span>Status</span><strong>{view.status}</strong></div>
        <div className="metric"><span>Source record</span><strong>{view.source_record_id}</strong></div>
        <div className="metric"><span>Observed at</span><strong>{view.observed_at ?? "Unknown"}</strong></div>
        <div className="metric"><span>Valid from</span><strong>{view.valid_from ?? "Unknown"}</strong></div>
        <div className="metric"><span>Valid to</span><strong>{view.valid_to ?? "Unknown"}</strong></div>
      </div>
      <label>
        Claim text
        <textarea value={text} onChange={(event) => setText(event.target.value)} rows={4} />
      </label>
      <label>
        Concept labels (comma-separated)
        <input value={conceptLabelsText} onChange={(event) => setConceptLabelsText(event.target.value)} />
      </label>
      <p className="eyebrow">Evidence</p>
      <EvidenceList evidence={view.evidence} />
      <ActionBar
        adapter="knowledge_proposal"
        allowedActions={pending.allowed_actions}
        descriptors={descriptors}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    </div>
  );
}

function RelationReview({ pending, payload, view, busy, submit, onUnsupported }: ProposalScaffold & { view: RelationProposalView }) {
  const [subject, setSubject] = useState(view.subject);
  const [predicate, setPredicate] = useState(view.predicate);
  const [object, setObject] = useState(view.object);

  const descriptors = useMemo<ActionDescriptor[]>(() => [
    { action: "approve", label: <>Approve <Check size={17} /></>, tone: "primary", buildPayload: () => ({}) },
    {
      action: "edit",
      label: <>Save edit <Pencil size={16} /></>,
      tone: "primary",
      disabled: !subject.trim() || !predicate.trim() || !object.trim(),
      buildPayload: () => ({
        edited_proposal: {
          ...payload.proposal,
          subject: subject.trim(),
          predicate: predicate.trim(),
          object: object.trim(),
        },
      }),
    },
    { action: "reject", label: "Reject", tone: "danger", buildPayload: () => ({}) },
  ], [object, payload.proposal, predicate, subject]);

  return (
    <div className="proposal-card">
      <div className="field-rows">
        <div className="metric"><span>Proposal type</span><strong>Relation</strong></div>
        <div className="metric"><span>Proposal confidence</span><strong>{confidenceLabel(payload.proposal_confidence)}</strong></div>
        <div className="metric"><span>Proposal id</span><strong>{view.proposal_id}</strong></div>
        <div className="metric"><span>Model confidence</span><strong>{confidenceLabel(view.model_confidence)}</strong></div>
        <div className="metric"><span>Status</span><strong>{view.status}</strong></div>
        <div className="metric"><span>Source record</span><strong>{view.source_record_id}</strong></div>
        <div className="metric"><span>Domain</span><strong>{view.domain ?? "Not tagged"}</strong></div>
        <div className="metric">
          <span>Hierarchical</span>
          <strong>{view.hierarchical ? "Yes — gates cycle detection" : "No"}</strong>
        </div>
      </div>
      <div className="edit-grid edit-grid-3">
        <label>
          Subject
          <input value={subject} onChange={(event) => setSubject(event.target.value)} />
        </label>
        <label>
          Predicate
          <input value={predicate} onChange={(event) => setPredicate(event.target.value)} />
        </label>
        <label>
          Object
          <input value={object} onChange={(event) => setObject(event.target.value)} />
        </label>
      </div>
      <p className="eyebrow">Evidence</p>
      <EvidenceList evidence={view.evidence} />
      <ActionBar
        adapter="knowledge_proposal"
        allowedActions={pending.allowed_actions}
        descriptors={descriptors}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    </div>
  );
}

/**
 * The coordinator's own contract is `proposal_type: "concept" | "claim" |
 * "relation"`, but `payload.proposal` is still `dict[str, Any]` on the wire —
 * a proposal whose type doesn't match its actual shape is a contract
 * violation, not a rendering edge case. It fails loudly, the same way
 * ActionBar fails loudly on an unrecognized action, rather than rendering a
 * blank or defaulted screen. No ActionBar renders here: nothing is safe to
 * submit against a payload shape that isn't understood.
 */
function UnrecognizedProposal({
  payload,
  onUnsupported,
}: {
  payload: KnowledgeProposalPayload;
  onUnsupported: (unsupported: UnsupportedActions | null) => void;
}) {
  // Whatever contract problem a previously mounted adapter raised no longer
  // applies to this one.
  useEffect(() => onUnsupported(null), [onUnsupported]);

  // No AdapterFrame of its own: the caller already provides one, shared with
  // every proposal in the envelope. This still renders under a heading that
  // says "knowledge proposals" rather than "contract failure" -- the error
  // banner itself, not the frame around it, is what has to carry that.
  return (
    <div className="proposal-card error-banner">
      <AlertTriangle size={18} />
      <span>
        The coordinator returned <code>proposal_type: {JSON.stringify(payload.proposal_type)}</code>,
        which this view does not know how to render or submit a decision for. This is a contract
        mismatch between the coordinator and the shell, not a missing feature — no action can be
        submitted safely until it is resolved.
      </span>
    </div>
  );
}

function EnvelopeReview({
  pending,
  payload,
  busy,
  submit,
  onUnsupported,
}: {
  pending: KnowledgeProposalPending;
  payload: KnowledgeEnvelopePayload;
  busy: boolean;
  submit: SubmitDecision;
  onUnsupported: (unsupported: UnsupportedActions | null) => void;
}) {
  const descriptors = useMemo<ActionDescriptor[]>(() => [
    { action: "approve", label: <>Approve envelope <Check size={17} /></>, tone: "primary", buildPayload: () => ({}) },
    { action: "reject", label: "Reject envelope", tone: "danger", buildPayload: () => ({}) },
  ], []);

  return (
    <AdapterFrame
      title="Review the knowledge envelope"
      eyebrow="Knowledge proposal · whole envelope"
      icon={<Sparkles />}
      aside={<Metric label="Model confidence" value={confidenceLabel(payload.model_confidence)} />}
    >
      <div className="field-rows">
        <div className="metric"><span>Source record</span><strong>{payload.source_record_id}</strong></div>
        <div className="metric"><span>Highlight index</span><strong>{payload.highlight_index ?? "Unknown"}</strong></div>
      </div>
      <HighlightWithEvidence text={payload.highlight_text ?? null} quote={null} start={null} end={null} />
      <section>
        <p className="eyebrow">Review signals</p>
        <SignalList signals={payload.review_signals} />
      </section>
      <p className="diag-empty">
        This is a whole-envelope decision — there is no per-field editing. Approving accepts every
        proposal below it for its own individual review; rejecting discards the envelope entirely.
      </p>
      <ActionBar
        adapter="knowledge_proposal"
        allowedActions={pending.allowed_actions}
        descriptors={descriptors}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    </AdapterFrame>
  );
}

function ProposalBody(scaffold: ProposalScaffold) {
  const { payload, onUnsupported } = scaffold;
  if (payload.proposal_type === "concept" && isConceptProposalView(payload.proposal)) {
    return <ConceptReview {...scaffold} view={payload.proposal} />;
  }
  if (payload.proposal_type === "claim" && isClaimProposalView(payload.proposal)) {
    return <ClaimReview {...scaffold} view={payload.proposal} />;
  }
  if (payload.proposal_type === "relation" && isRelationProposalView(payload.proposal)) {
    return <RelationReview {...scaffold} view={payload.proposal} />;
  }
  return <UnrecognizedProposal payload={payload} onUnsupported={onUnsupported} />;
}

/**
 * One highlight can produce several proposals (a claim, one or more
 * concepts, relations). The coordinator still surfaces and decides exactly
 * one at a time (`gates.py`'s single-pending-item invariant is unchanged),
 * but `App.tsx` now keys this whole component on the envelope rather than
 * the individual proposal, so this frame -- and the highlight/evidence it
 * shows -- mounts once per envelope instead of once per proposal. Only the
 * proposal-specific body underneath is keyed by `proposal_id`, so its local
 * edit state (a label, a claim's text) never survives into the next
 * proposal's initial render.
 */
export function KnowledgeProposalReview({
  pending,
  busy,
  submit,
  onUnsupported,
  token,
  runId,
}: AdapterProps<KnowledgeProposalPending> & { token: string; runId: string }) {
  const { payload } = pending;

  if (isKnowledgeEnvelopePayload(payload)) {
    return (
      <EnvelopeReview
        pending={pending}
        payload={payload}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    );
  }

  return (
    <AdapterFrame
      title="Review this highlight's knowledge proposals"
      eyebrow="Knowledge proposal"
      icon={<Layers />}
      aside={<Metric label="Envelope confidence" value={confidenceLabel(payload.envelope_confidence)} />}
    >
      <ProposalContext payload={payload} />
      {payload.photo_page_id !== null && payload.photo_page_id !== undefined && (
        <ProposalPhotoPanel payload={payload} token={token} runId={runId} itemId={pending.item_id} />
      )}
      <ProposalRoadmap
        current={{ proposal_id: payload.proposal_id, proposal_type: payload.proposal_type }}
        siblings={payload.sibling_proposals}
      />
      <ProposalBody
        key={payload.proposal_id}
        pending={pending}
        payload={payload}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    </AdapterFrame>
  );
}
