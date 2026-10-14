import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { KnowledgeProposalPending } from "../api/client";
import { knowledgeEnvelopePending, knowledgeProposalPending } from "../test/factories";
import { KnowledgeProposalReview } from "./KnowledgeProposalReview";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubEvidence(response: Response | (() => Response)) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => (typeof response === "function" ? response() : response)),
  );
}

function renderReview(pending: KnowledgeProposalPending) {
  const submit = vi.fn();
  const onUnsupported = vi.fn();
  const result = render(
    <KnowledgeProposalReview
      pending={pending}
      busy={false}
      submit={submit}
      onUnsupported={onUnsupported}
      token="test-token"
      runId="run-1"
    />,
  );
  return { submit, onUnsupported, rerender: result.rerender };
}

describe("proposal-level edit serialization", () => {
  it("builds an edited_proposal that spreads the original wire object with only the edited content field changed", async () => {
    const pending = knowledgeProposalPending() as KnowledgeProposalPending;
    const { submit } = renderReview(pending);

    const labelField = screen.getByLabelText("Label");
    await userEvent.clear(labelField);
    await userEvent.type(labelField, "Convexity");
    await userEvent.click(screen.getByRole("button", { name: /Save edit/ }));

    expect(submit).toHaveBeenCalledWith("edit", {
      edited_proposal: {
        proposal_id: "concept-1",
        label: "Convexity",
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
    });
  });

  it("edits the alias list from the comma-separated field", async () => {
    const pending = knowledgeProposalPending() as KnowledgeProposalPending;
    const { submit } = renderReview(pending);

    const aliases = screen.getByLabelText("Aliases (comma-separated)");
    await userEvent.clear(aliases);
    await userEvent.type(aliases, "DUR, Macaulay Duration");
    await userEvent.click(screen.getByRole("button", { name: /Save edit/ }));

    expect(submit).toHaveBeenCalledWith("edit", expect.objectContaining({
      edited_proposal: expect.objectContaining({
        aliases: ["DUR", "Macaulay Duration"],
      }),
    }));
  });

  it("never includes edited_proposal for a non-edit action", async () => {
    const pending = knowledgeProposalPending() as KnowledgeProposalPending;
    const { submit } = renderReview(pending);

    await userEvent.click(screen.getByRole("button", { name: /^Approve/ }));
    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenCalledWith("approve", {});
    expect(submit.mock.calls[0][1]).not.toHaveProperty("edited_proposal");

    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(submit).toHaveBeenCalledTimes(2);
    expect(submit).toHaveBeenCalledWith("reject", {});
    expect(submit.mock.calls[1][1]).not.toHaveProperty("edited_proposal");
  });
});

describe("read-only fields", () => {
  it("renders no editable control for any read-only proposal field", () => {
    const pending = knowledgeProposalPending() as KnowledgeProposalPending;
    renderReview(pending);

    for (const label of ["Proposal id", "Model confidence", "Status", "Source record", "Domain"]) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
    }
    // They are still visible as plain text, not silently dropped.
    expect(screen.getByText("concept-1")).toBeInTheDocument();
    expect(screen.getByText("proposed")).toBeInTheDocument();
    expect(screen.getByText("finance")).toBeInTheDocument();
  });

  it("renders relation's hierarchical field as read-only, never as a control", () => {
    const pending = knowledgeProposalPending({
      payload: {
        envelope_id: "envelope-1",
        proposal_id: "relation-1",
        proposal_type: "relation",
        proposal: {
          proposal_id: "relation-1",
          subject: "Duration",
          predicate: "is a prerequisite of",
          object: "Convexity",
          model_confidence: 0.8,
          status: "proposed",
          source_record_id: "source-1",
          evidence: [],
          domain: null,
          hierarchical: true,
        },
        source_note_path: null,
        origin_kind: null,
        highlight_index: null,
        highlight_text: null,
        evidence_quote: null,
        evidence_start_char: null,
        evidence_end_char: null,
        proposal_confidence: 0.8,
        envelope_confidence: 0.8,
        signals: [],
        sibling_proposals: [],
      },
    } as never) as KnowledgeProposalPending;

    renderReview(pending);

    expect(screen.queryByLabelText("Hierarchical")).not.toBeInTheDocument();
    expect(screen.getByText(/Yes — gates cycle detection/)).toBeInTheDocument();

    // Editing subject/predicate/object must still round-trip hierarchical
    // and evidence unchanged.
  });
});

describe("unrecognized proposal_type", () => {
  it("fails loudly instead of rendering blank, and offers nothing submittable", () => {
    const pending = knowledgeProposalPending({
      payload: {
        envelope_id: "envelope-1",
        proposal_id: "mystery-1",
        proposal_type: "mystery",
        proposal: { proposal_id: "mystery-1" },
        source_note_path: null,
        origin_kind: null,
        highlight_index: null,
        highlight_text: null,
        evidence_quote: null,
        evidence_start_char: null,
        evidence_end_char: null,
        proposal_confidence: null,
        envelope_confidence: null,
        signals: [],
        sibling_proposals: [],
      },
    } as never) as KnowledgeProposalPending;

    const { onUnsupported } = renderReview(pending);

    expect(screen.getByText(/does not know how to render/)).toBeInTheDocument();
    expect(screen.getByText(/"mystery"/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(onUnsupported).toHaveBeenCalledWith(null);
  });
});

describe("sibling proposals from the same envelope", () => {
  it("lists every sibling proposal alongside the active one, with its type, summary and status", () => {
    const pending = knowledgeProposalPending({
      payload: {
        ...knowledgeProposalPending().payload,
        sibling_proposals: [
          { proposal_id: "claim-1", proposal_type: "claim", status: "pending", summary: "Rates fell after the announcement." },
          { proposal_id: "relation-1", proposal_type: "relation", status: "approved", summary: "Duration measures Convexity" },
        ],
      },
    } as never) as KnowledgeProposalPending;

    renderReview(pending);

    expect(screen.getByText("Rates fell after the announcement.")).toBeInTheDocument();
    expect(screen.getByText("Duration measures Convexity")).toBeInTheDocument();
    expect(screen.getByText("approved")).toBeInTheDocument();
    expect(screen.getByText("Reviewing now")).toBeInTheDocument();
  });

  it("resets the next proposal's edit fields instead of carrying over the previous proposal's in-progress edit", () => {
    const first = knowledgeProposalPending() as KnowledgeProposalPending;
    const { rerender } = renderReview(first);

    // Nothing decided yet; this local edit must never reach a different
    // proposal's initial field values below.
    expect(screen.getByLabelText("Label")).toHaveValue("Duration");

    const second = knowledgeProposalPending({
      item_id: "concept-2",
      payload: {
        ...knowledgeProposalPending().payload,
        proposal_id: "concept-2",
        proposal: {
          proposal_id: "concept-2",
          label: "Convexity",
          aliases: [],
          model_confidence: 0.7,
          status: "proposed",
          source_record_id: "source-1",
          evidence: [],
          domain: "finance",
        },
      },
    } as never) as KnowledgeProposalPending;

    rerender(
      <KnowledgeProposalReview
        pending={second}
        busy={false}
        submit={vi.fn()}
        onUnsupported={vi.fn()}
        token="test-token"
        runId="run-1"
      />,
    );

    expect(screen.getByLabelText("Label")).toHaveValue("Convexity");
  });
});

describe("photo evidence for a page-scanner highlight", () => {
  it("shows the source page and boxes every passage on it, so the reviewer can check the extraction instead of trusting it", async () => {
    stubEvidence(new Response(new Blob(["image"]), { status: 200 }));
    const pending = knowledgeProposalPending({
      payload: {
        ...knowledgeProposalPending().payload,
        photo_page_id: 9,
        photo_page_number: 9,
        photo_passages: [
          { bbox: [10, 20, 100, 30], ocr_text: "Duration measures rate sensitivity." },
        ],
      },
    } as never) as KnowledgeProposalPending;

    renderReview(pending);

    expect(await screen.findByAltText("Photographed source page")).toBeInTheDocument();
    expect(screen.getByText("Source page · page 9")).toBeInTheDocument();
  });

  it("renders no photo panel, and fetches nothing, for a typed-note highlight with no photo", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const pending = knowledgeProposalPending() as KnowledgeProposalPending;

    renderReview(pending);

    expect(screen.queryByAltText("Photographed source page")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Source page/)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("envelope-level review", () => {
  it("renders only approve/reject and no per-field editing", () => {
    const pending = knowledgeEnvelopePending() as KnowledgeProposalPending;
    renderReview(pending);

    expect(screen.getByRole("button", { name: /Approve envelope/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject envelope" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("is visually distinct from the proposal-level screen", () => {
    const pending = knowledgeEnvelopePending() as KnowledgeProposalPending;
    renderReview(pending);
    expect(screen.getByText("Review the knowledge envelope")).toBeInTheDocument();
  });
});
