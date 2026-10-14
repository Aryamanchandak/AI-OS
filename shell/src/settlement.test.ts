import { describe, expect, it } from "vitest";

import { isValidConfirmation, settle, type PendingConfirmation } from "./settlement";
import { bookPending, cleanupPending, imagePending, snapshot, view } from "./test/factories";

const submitted: PendingConfirmation = {
  runId: "run-1",
  itemId: "image-1",
  adapter: "image_ocr",
  action: "approve",
  submittedRevision: 3,
};

describe("settle", () => {
  it("waits while the operation is still in flight", () => {
    const inFlight = snapshot({ operation: { state: "submitting", name: "decision", revision: 3 } });
    expect(settle(submitted, inFlight)).toEqual({ state: "waiting" });
  });

  it("confirms only when the revision advanced by one and the item is gone", () => {
    const settled = snapshot({
      view: view({ pending: null, terminal_result: "complete" }),
      operation: { state: "idle", revision: 4 },
    });
    expect(settle(submitted, settled)).toEqual({ state: "confirmed" });
  });

  it("reports a failure when the background operation failed after the 202", () => {
    const failed = snapshot({
      operation: { state: "failed", name: "decision", error: "Neo4j refused the write", revision: 3 },
    });
    const outcome = settle(submitted, failed);
    expect(outcome.state).toBe("failed");
    expect(outcome).toMatchObject({ reason: "Neo4j refused the write" });
  });

  it("reports a failure when the coordinator recorded a stage error", () => {
    const failed = snapshot({
      view: view({
        pending: null,
        last_error: { stage: "capture_obsidian", message: "vault is read-only", retryable: true },
      }),
      operation: { state: "idle", revision: 4 },
    });
    const outcome = settle(submitted, failed);
    expect(outcome.state).toBe("failed");
    expect(outcome).toMatchObject({ reason: "capture_obsidian failed: vault is read-only" });
  });

  it("refuses to confirm when the revision does not match the submission", () => {
    const drifted = snapshot({
      view: view({ pending: null }),
      operation: { state: "idle", revision: 9 },
    });
    const outcome = settle(submitted, drifted);
    expect(outcome.state).toBe("mismatch");
    expect(outcome).toMatchObject({
      reason: expect.stringContaining("Expected revision 4"),
    });
  });

  it("refuses to confirm while the same item is still pending", () => {
    const stillPending = snapshot({ operation: { state: "idle", revision: 4 } });
    const outcome = settle(submitted, stillPending);
    expect(outcome.state).toBe("mismatch");
    expect(outcome).toMatchObject({ reason: "image-1 is still awaiting a decision." });
  });

  it("refuses to confirm when the run changed underneath the submission", () => {
    const otherRun = snapshot({
      view: view({ run_id: "run-2", pending: null }),
      operation: { state: "idle", revision: 4 },
    });
    expect(settle(submitted, otherRun).state).toBe("mismatch");
  });

  it("waits rather than confirming when there is no snapshot at all", () => {
    expect(settle(submitted, null)).toEqual({ state: "waiting" });
  });
});

describe("settle: cleanup same-item confirmation (C8-C2)", () => {
  const submittedApply: PendingConfirmation = {
    runId: "run-1",
    itemId: "cleanup-1",
    adapter: "cleanup",
    action: "apply_once",
    submittedRevision: 3,
    cleanupInteractionRevision: 0,
  };

  it("confirms a per-occurrence action when the same item stays pending with a higher interaction_revision", () => {
    const settled = snapshot({
      view: view({ pending: cleanupPending({}, { interaction_revision: 1 }) }),
      operation: { state: "idle", revision: 4 },
    });
    expect(settle(submittedApply, settled)).toEqual({ state: "confirmed" });
  });

  it("does not confirm when the item stays pending but interaction_revision has not advanced", () => {
    const unchanged = snapshot({
      view: view({ pending: cleanupPending() }), // interaction_revision still 0
      operation: { state: "idle", revision: 4 },
    });
    const outcome = settle(submittedApply, unchanged);
    expect(outcome.state).toBe("mismatch");
  });

  it("does not confirm when the item left the cleanup adapter without a Continue decision", () => {
    const wrongAdapter = snapshot({
      view: view({ pending: imagePending({ item_id: "cleanup-1" }) }),
      operation: { state: "idle", revision: 4 },
    });
    const outcome = settle(submittedApply, wrongAdapter);
    expect(outcome.state).toBe("mismatch");
  });

  it("does not confirm when the item disappeared for a non-continue action", () => {
    const gone = snapshot({
      view: view({ pending: null }),
      operation: { state: "idle", revision: 4 },
    });
    const outcome = settle(submittedApply, gone);
    expect(outcome.state).toBe("mismatch");
  });

  const submittedContinue: PendingConfirmation = {
    runId: "run-1",
    itemId: "cleanup-1",
    adapter: "cleanup",
    action: "continue",
    submittedRevision: 3,
    cleanupInteractionRevision: 5,
  };

  it("confirms Continue when the item is gone entirely", () => {
    const gone = snapshot({
      view: view({ pending: null, terminal_result: "complete" }),
      operation: { state: "idle", revision: 4 },
    });
    expect(settle(submittedContinue, gone)).toEqual({ state: "confirmed" });
  });

  it("confirms Continue when the same item transitioned to its legal final-review adapter", () => {
    const transitioned = snapshot({
      view: view({ pending: imagePending({ item_id: "cleanup-1" }) }),
      operation: { state: "idle", revision: 4 },
    });
    expect(settle(submittedContinue, transitioned)).toEqual({ state: "confirmed" });
  });

  it("rejects Continue when the same item transitioned to a non-final adapter", () => {
    const wrongAdapter = snapshot({
      view: view({
        pending: bookPending({ item_id: "cleanup-1" }),
      }),
      operation: { state: "idle", revision: 4 },
    });
    expect(settle(submittedContinue, wrongAdapter).state).toBe("mismatch");
  });

  it("confirms Continue when the coordinator moved on to a different item entirely", () => {
    const movedOn = snapshot({
      view: view({ pending: cleanupPending({ item_id: "cleanup-2" }) }),
      operation: { state: "idle", revision: 4 },
    });
    expect(settle(submittedContinue, movedOn)).toEqual({ state: "confirmed" });
  });

  it("does not confirm Continue when the same item is still on the cleanup adapter", () => {
    const stillCleanup = snapshot({
      view: view({ pending: cleanupPending() }),
      operation: { state: "idle", revision: 4 },
    });
    const outcome = settle(submittedContinue, stillCleanup);
    expect(outcome.state).toBe("mismatch");
  });

  it("confirms Retry when a clean result advances the same item to final review", () => {
    const submittedRetry = { ...submittedApply, action: "retry" };
    const transitioned = snapshot({
      view: view({ pending: imagePending({ item_id: "cleanup-1" }) }),
      operation: { state: "idle", revision: 4 },
    });
    expect(settle(submittedRetry, transitioned)).toEqual({ state: "confirmed" });
  });

  it("rejects Retry when the same item reaches an unrelated adapter", () => {
    const submittedRetry = { ...submittedApply, action: "retry" };
    const wrongAdapter = snapshot({
      view: view({
        pending: bookPending({ item_id: "cleanup-1" }),
      }),
      operation: { state: "idle", revision: 4 },
    });
    expect(settle(submittedRetry, wrongAdapter).state).toBe("mismatch");
  });

  it("still requires the generic revision-plus-one check before any cleanup-specific rule", () => {
    const drifted = snapshot({
      view: view({ pending: cleanupPending() }),
      operation: { state: "idle", revision: 9 },
    });
    expect(settle(submittedApply, drifted).state).toBe("mismatch");
  });

  it("ordinary adapters are unaffected by the cleanup same-item rule", () => {
    const submitted: PendingConfirmation = {
      runId: "run-1",
      itemId: "image-1",
      adapter: "image_ocr",
      action: "approve",
      submittedRevision: 3,
    };
    const stillPending = snapshot({ operation: { state: "idle", revision: 4 } });
    const outcome = settle(submitted, stillPending);
    expect(outcome.state).toBe("mismatch");
    expect(outcome).toMatchObject({ reason: "image-1 is still awaiting a decision." });
  });
});

describe("isValidConfirmation", () => {
  it("accepts a complete record", () => {
    expect(isValidConfirmation(submitted)).toBe(true);
  });

  it.each([
    ["null", null],
    ["an empty object", {}],
    ["an array", []],
    ["a missing revision", { runId: "r", itemId: "i", adapter: "a", action: "approve" }],
    ["a non-numeric revision", { ...submitted, submittedRevision: "3" }],
    ["a non-numeric cleanupInteractionRevision", { ...submitted, cleanupInteractionRevision: "0" }],
  ])("rejects %s", (_label, value) => {
    expect(isValidConfirmation(value)).toBe(false);
  });

  it("accepts a cleanup record with cleanupInteractionRevision", () => {
    expect(isValidConfirmation({ ...submitted, adapter: "cleanup", cleanupInteractionRevision: 0 })).toBe(true);
  });
});
