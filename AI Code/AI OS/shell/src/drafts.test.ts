import { describe, expect, it } from "vitest";

import {
  clearDraft,
  clearSubmission,
  draftKey,
  findOutstandingSubmission,
  markSubmitted,
  readDraft,
  writeDraft,
} from "./drafts";
import type { PendingConfirmation } from "./settlement";

type Passage = { index: number; edited_text: string };

function isPassages(value: unknown): value is Passage[] {
  return Array.isArray(value) && value.every((item) => (
    typeof item === "object" && item !== null
    && typeof (item as Passage).index === "number"
    && typeof (item as Passage).edited_text === "string"
  ));
}

const passages: Passage[] = [{ index: 0, edited_text: "Edited by hand" }];

const submission: PendingConfirmation = {
  runId: "run-1",
  itemId: "image-1",
  adapter: "image_ocr",
  action: "approve",
  submittedRevision: 3,
};

describe("draft storage", () => {
  it("keys drafts by run and item", () => {
    expect(draftKey("run-1", "image-1")).toBe("ai-os:ingestion:draft:run-1:image-1");
  });

  it("round-trips a draft", () => {
    writeDraft("run-1", "image-1", { value: passages, pending: null });
    const read = readDraft("run-1", "image-1", isPassages);
    expect(read).toEqual({ status: "ok", record: { value: passages, pending: null } });
  });

  it("keeps runs and items isolated from each other", () => {
    writeDraft("run-1", "image-1", { value: passages, pending: null });
    expect(readDraft("run-2", "image-1", isPassages).status).toBe("empty");
    expect(readDraft("run-1", "image-2", isPassages).status).toBe("empty");
  });

  it("clears only the exact matching draft", () => {
    writeDraft("run-1", "image-1", { value: passages, pending: null });
    writeDraft("run-1", "image-2", { value: passages, pending: null });
    writeDraft("run-2", "image-1", { value: passages, pending: null });

    clearDraft("run-1", "image-1");

    expect(readDraft("run-1", "image-1", isPassages).status).toBe("empty");
    // Orphaned drafts are left for manual removal, never bulk-deleted.
    expect(readDraft("run-1", "image-2", isPassages).status).toBe("ok");
    expect(readDraft("run-2", "image-1", isPassages).status).toBe("ok");
  });

  it.each([
    ["unparseable text", "{not json"],
    ["a JSON null", "null"],
    ["a bare array", "[1,2,3]"],
    ["a value of the wrong shape", JSON.stringify({ value: { nope: true }, pending: null })],
    ["a value that is a string", JSON.stringify({ value: "passages", pending: null })],
    ["an incomplete submission record", JSON.stringify({ value: passages, pending: { runId: "run-1" } })],
  ])("reports %s as corrupt instead of throwing", (_label, raw) => {
    sessionStorage.setItem(draftKey("run-1", "image-1"), raw);
    const read = readDraft("run-1", "image-1", isPassages);
    expect(read.status).toBe("corrupt");
    expect(read).toMatchObject({ reason: expect.any(String) });
  });

  it("treats a submission-only record as a valid draft with no value", () => {
    markSubmitted("run-1", "book-1", { ...submission, itemId: "book-1", adapter: "book_identity", action: "confirm" });
    const read = readDraft("run-1", "book-1", isPassages);
    expect(read).toMatchObject({ status: "ok", record: { value: null } });
  });

  it("attaches a submission without discarding existing edits", () => {
    writeDraft("run-1", "image-1", { value: passages, pending: null });
    markSubmitted("run-1", "image-1", submission);
    const read = readDraft("run-1", "image-1", isPassages);
    expect(read).toEqual({ status: "ok", record: { value: passages, pending: submission } });
  });

  it("round-trips a cleanup submission's interaction_revision (component_8.md section 8.5)", () => {
    const cleanupSubmission: PendingConfirmation = {
      runId: "run-1",
      itemId: "cleanup-1",
      adapter: "cleanup",
      action: "apply_once",
      submittedRevision: 3,
      cleanupInteractionRevision: 2,
    };
    markSubmitted("run-1", "cleanup-1", cleanupSubmission);
    const read = readDraft("run-1", "cleanup-1", isPassages);
    expect(read).toMatchObject({ status: "ok", record: { pending: cleanupSubmission } });
  });
});

describe("outstanding submission reconciliation", () => {
  it("finds an accepted-but-unsettled submission for the run after a refresh", () => {
    writeDraft("run-1", "image-1", { value: passages, pending: submission });
    expect(findOutstandingSubmission("run-1")).toEqual(submission);
  });

  it("does not adopt another run's outstanding submission", () => {
    writeDraft("run-1", "image-1", { value: passages, pending: submission });
    expect(findOutstandingSubmission("run-2")).toBeNull();
  });

  it("ignores drafts with no outstanding submission", () => {
    writeDraft("run-1", "image-1", { value: passages, pending: null });
    expect(findOutstandingSubmission("run-1")).toBeNull();
  });

  it("forgets a settled submission while retaining the draft", () => {
    writeDraft("run-1", "image-1", { value: passages, pending: submission });
    clearSubmission("run-1", "image-1");

    expect(findOutstandingSubmission("run-1")).toBeNull();
    expect(readDraft("run-1", "image-1", isPassages)).toEqual({
      status: "ok",
      record: { value: passages, pending: null },
    });
  });

  it("skips corrupt entries rather than failing the scan", () => {
    sessionStorage.setItem(draftKey("run-1", "image-0"), "{not json");
    writeDraft("run-1", "image-1", { value: passages, pending: submission });
    expect(findOutstandingSubmission("run-1")).toEqual(submission);
  });
});
