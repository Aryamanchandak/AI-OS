import type { Pending, RunReport, Snapshot, View } from "../api/client";

export function imagePending(overrides: Partial<Pending> = {}): Pending {
  return {
    item_id: "image-1",
    item_type: "image",
    gate: "content_approval",
    adapter: "image_ocr",
    allowed_actions: ["approve", "retake", "discard"],
    blocking_reason: "approval required",
    payload: {
      photo_path: "/tmp/page.jpg",
      page_number: 42,
      conf_ratio: 0.04,
      blur_score: 180,
      glare_score: 0.01,
      passages: [
        { index: 0, ocr_text: "We become what we notlce.", edited_text: "We become what we notice.", bbox: [1, 2, 3, 4], min_conf: 0.9 },
      ],
    },
    ...overrides,
  } as Pending;
}

export function bookPending(overrides: Partial<Pending> = {}): Pending {
  return {
    item_id: "book-1",
    item_type: "book",
    gate: "book_metadata",
    adapter: "book_identity",
    allowed_actions: ["confirm", "correct"],
    blocking_reason: "book identity must be confirmed",
    payload: {
      photo_count: 4,
      proposed_title: "The Shape of Attention",
      proposed_author: "A. Chandak",
      proposed_year: 2026,
      confidence: "fuzzy",
      meta_source: "local",
      resolved_slug: "the-shape-of-attention",
    },
    ...overrides,
  } as Pending;
}

export function textPending(overrides: Partial<Pending> = {}): Pending {
  return {
    item_id: "text-1",
    item_type: "text",
    gate: "content_approval",
    adapter: "text_file",
    allowed_actions: ["approve", "discard"],
    blocking_reason: "approval required",
    payload: {
      source_path: "/tmp/notes.pdf",
      markdown_text: "# Notes",
      warnings: [],
    },
    ...overrides,
  } as Pending;
}

export function cleanupPending(
  overrides: Partial<Pending> = {},
  payloadOverrides: Record<string, unknown> = {},
): Pending {
  return {
    item_id: "cleanup-1",
    item_type: "file",
    gate: "cleanup",
    adapter: "cleanup",
    allowed_actions: ["apply_once", "apply_remember", "skip", "previous", "next"],
    blocking_reason: "abbreviation review required",
    payload: {
      state: "review",
      source_kind: "text_file",
      phase: "abbreviation",
      interaction_revision: 0,
      working_draft_revision: 0,
      occurrence: {
        occurrence_id: "abbr-p0-5-7-1",
        ordinal: 1,
        total: 1,
        passage_index: null,
        base_start: 5,
        base_end: 7,
        current_start: 5,
        current_end: 7,
        original_text: "w/",
        proposed_text: "with",
        context_before: "Talk ",
        context_after: " me soon.",
        before_sentence: "",
        after_sentence: "",
        current_decision: null,
        mapping_id: "mapping-1",
        proposal_source: "mapping:mapping-1",
      },
      authoritative_sentence: "Talk w/ me soon.",
      authoritative_working_text: "Talk w/ me soon.",
      can_continue: false,
      ...payloadOverrides,
    },
    ...overrides,
  } as Pending;
}

export function cleanupUnavailablePending(overrides: Partial<Pending> = {}): Pending {
  return {
    item_id: "cleanup-1",
    item_type: "file",
    gate: "cleanup",
    adapter: "cleanup",
    allowed_actions: ["retry"],
    blocking_reason: "the spelling checker is unavailable",
    payload: {
      state: "unavailable",
      source_kind: "text_file",
      phase: "spelling",
      interaction_revision: 1,
      working_draft_revision: 1,
      error: "spelling gateway call failed",
    },
    ...overrides,
  } as Pending;
}

export function phaseHandoffPending(overrides: Partial<Pending> = {}): Pending {
  return {
    item_id: "",
    item_type: "phase_handoff",
    gate: "phase_handoff",
    adapter: "phase_handoff",
    allowed_actions: ["continue", "stop"],
    blocking_reason: "intake is complete; choose whether to continue",
    payload: {
      discovered: 4,
      published: 3,
      discarded: 1,
      retake: 0,
      duplicate: 0,
      failed: 0,
      note_paths: ["vault/note-1.md", "vault/note-2.md"],
    },
    ...overrides,
  } as Pending;
}

export function knowledgeEnvelopePending(overrides: Partial<Pending> = {}): Pending {
  return {
    item_id: "envelope-1",
    item_type: "envelope",
    gate: "proposal",
    adapter: "knowledge_proposal",
    allowed_actions: ["approve", "reject"],
    blocking_reason: "semantic envelope requires review",
    payload: {
      envelope_level: true,
      review_signals: [
        { code: "empty_semantic_extraction", scope: "envelope" },
      ],
      source_record_id: "source-1",
      highlight_index: 0,
      highlight_text: "Duration measures rate sensitivity.",
      model_confidence: 0.42,
    },
    ...overrides,
  } as Pending;
}

export function knowledgeProposalPending(overrides: Partial<Pending> = {}): Pending {
  return {
    item_id: "concept-1",
    item_type: "proposal",
    gate: "proposal",
    adapter: "knowledge_proposal",
    allowed_actions: ["approve", "edit", "reject"],
    blocking_reason: "semantic proposal requires review",
    payload: {
      envelope_id: "envelope-1",
      proposal_id: "concept-1",
      proposal_type: "concept",
      proposal: {
        proposal_id: "concept-1",
        label: "Duration",
        aliases: ["DUR"],
        model_confidence: 0.91,
        status: "proposed",
        source_record_id: "source-1",
        evidence: [
          {
            source_record_id: "source-1",
            quote: "Duration measures",
            normalized_char_start: 0,
            normalized_char_end: 18,
          },
        ],
        domain: "finance",
      },
      source_note_path: "vault/Bonds.md",
      origin_kind: "page_scanner",
      highlight_index: 0,
      highlight_text: "Duration measures rate sensitivity.",
      evidence_quote: "Duration measures",
      evidence_start_char: 0,
      evidence_end_char: 18,
      proposal_confidence: 0.91,
      envelope_confidence: 0.87,
      signals: [
        { code: "alias_or_identity_proposal", scope: "proposal", proposal_id: "concept-1" },
      ],
      sibling_proposals: [],
    },
    ...overrides,
  } as Pending;
}

export function view(overrides: Partial<View> = {}): View {
  return {
    run_id: "run-1",
    stage: "intake_item",
    stage_status: "blocked",
    stages: [{ stage: "intake_item", status: "blocked", detail: {} }],
    pending: imagePending(),
    progress: {
      intake_total: 2,
      intake_resolved: 1,
      envelopes_flagged: 0,
      envelopes_resolved: 0,
    },
    last_error: null,
    terminal_result: null,
    ...overrides,
  };
}

export function snapshot(overrides: {
  view?: View | null;
  operation?: Partial<Snapshot["operation"]>;
} = {}): Snapshot {
  return {
    contract_version: "component6.v1",
    reviewer: "local-reviewer",
    view: overrides.view === undefined ? view() : overrides.view,
    operation: {
      state: "idle",
      name: null,
      error: null,
      revision: 3,
      ...overrides.operation,
    },
  };
}

export function runReport(overrides: Partial<RunReport> = {}): RunReport {
  return {
    run_id: "run-1",
    terminal_result: "complete",
    failed_from: null,
    last_error: null,
    stages: [
      { stage: "intake_item", status: "done", detail: { items: 2 } },
      { stage: "dispatch_retry", status: "skipped", detail: {} },
    ],
    intake: {
      discovered: 2, published: 2, discarded: 0, retake: 0, duplicate: 0, failed: 0,
      items: [], gates: [],
    },
    vault_notes_written: ["vault/note.md"],
    capture: [],
    capture_counts: { total: 1, new: 1, duplicate: 0 },
    processing: [],
    processing_counts: { published: 1 },
    review: { approve: 1, edit: 0, reject: 0, still_blocked: 0 },
    dispatch_counts: {},
    retryable_failures: [],
    discrepancies: [],
    progress: {
      intake_total: 2, intake_resolved: 2, envelopes_flagged: 0, envelopes_resolved: 0,
    },
    ...overrides,
  };
}
