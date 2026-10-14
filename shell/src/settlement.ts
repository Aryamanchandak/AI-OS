import type { Snapshot } from "./api/client";

/**
 * What the shell submitted and is still waiting on. A 202 response creates this
 * record; it means "accepted for processing" and nothing more. No success
 * indicator — celebration, draft clearing, completion copy — may fire from it.
 */
export type PendingConfirmation = {
  runId: string;
  itemId: string;
  adapter: string;
  action: string;
  /** The revision at submission time. Confirmed success is exactly this + 1. */
  submittedRevision: number;
  /**
   * Cleanup only: the item's interaction_revision at submission time. Every
   * cleanup action except Continue leaves the same item pending by design
   * (component_8.md section 8.5, C8-C2) — confirmation for those is a
   * strictly higher interaction_revision, not the item disappearing.
   */
  cleanupInteractionRevision?: number;
};

export type Settlement =
  /** The backend has not settled the operation yet. */
  | { state: "waiting" }
  /** The backend confirmed this exact decision completed. */
  | { state: "confirmed" }
  /** The backend settled, and this decision did not succeed. */
  | { state: "failed"; reason: string }
  /**
   * The backend settled into a state that is not this decision's outcome — a
   * different run, an unexpected revision, or the same item still pending.
   * Treated as "not success", never carried forward to a later operation.
   */
  | { state: "mismatch"; reason: string };

export function isValidConfirmation(value: unknown): value is PendingConfirmation {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.runId === "string"
    && typeof record.itemId === "string"
    && typeof record.adapter === "string"
    && typeof record.action === "string"
    && typeof record.submittedRevision === "number"
    && Number.isFinite(record.submittedRevision)
    && (record.cleanupInteractionRevision === undefined
      || (typeof record.cleanupInteractionRevision === "number"
        && Number.isFinite(record.cleanupInteractionRevision)))
  );
}

/**
 * Decide whether a submitted decision has been confirmed by the backend.
 *
 * Applies checks 2-5 of the stream's confirmed-success rule. Check 1 (which
 * adapter and action may celebrate) is a presentation decision and belongs to
 * the caller, because draft settlement uses the same rule for every adapter.
 */
export function settle(
  record: PendingConfirmation,
  snapshot: Snapshot | null,
): Settlement {
  if (!snapshot) return { state: "waiting" };
  const { operation, view } = snapshot;

  // Check 2: the operation must have settled.
  if (operation.state === "submitting") return { state: "waiting" };

  // Check 5a: an explicit service failure is a failure, whatever the revision.
  if (operation.state === "failed") {
    return {
      state: "failed",
      reason: operation.error ?? `${operation.name ?? "The operation"} failed.`,
    };
  }

  if (!view) return { state: "waiting" };

  // The run changed underneath the submission. Its outcome is unknowable.
  if (view.run_id !== record.runId) {
    return {
      state: "mismatch",
      reason: `Run ${record.runId} was replaced by run ${view.run_id} before this decision settled.`,
    };
  }

  // Check 5b: a coordinator stage error on this run blocks confirmation.
  if (view.last_error) {
    return {
      state: "failed",
      reason: `${view.last_error.stage} failed: ${view.last_error.message}`,
    };
  }

  // Check 3: the coordinator increments the revision only on a completed
  // operation, so confirmed success is exactly the submitted revision plus one.
  //
  // Below that, nothing has completed yet. This is the snapshot a poll returns
  // in the moment between the 202 and the operation being picked up, and it
  // must not be mistaken for a settled outcome in either direction.
  if (operation.revision < record.submittedRevision + 1) return { state: "waiting" };

  if (operation.revision > record.submittedRevision + 1) {
    return {
      state: "mismatch",
      reason:
        `Expected revision ${record.submittedRevision + 1} to confirm this decision, `
        + `but the run is at revision ${operation.revision}.`,
    };
  }

  // Check 4/6 for cleanup: unlike every other adapter, most cleanup actions
  // are *supposed* to leave the same item pending (component_8.md section
  // 8.5, C8-C2) — one backend mutation per occurrence/navigation, the item
  // only truly leaves the queue on Continue. "Still pending" therefore means
  // something different depending on which action was submitted.
  if (record.adapter === "cleanup") {
    const pending = view.pending;

    if (record.action === "continue") {
      // Confirmed when the item left cleanup's queue entirely (gone, or the
      // coordinator moved on to a different item) or landed on its legal
      // final-review adapter. Any other adapter retaining the same item is a
      // mismatch — Continue did not produce its promised boundary.
      if (pending !== null && pending.item_id === record.itemId) {
        if (pending.adapter === "image_ocr" || pending.adapter === "text_file") {
          return { state: "confirmed" };
        }
        return {
          state: "mismatch",
          reason: `${record.itemId} did not reach a legal final-review adapter after Continue.`,
        };
      }
      return { state: "confirmed" };
    }

    if (record.action === "retry") {
      // A successful retry may either produce another cleanup payload or find
      // zero suggestions and advance directly to final approval. Both are
      // legal; an unrelated same-item adapter is not.
      if (pending !== null && pending.item_id === record.itemId) {
        if (pending.adapter === "cleanup") {
          const confirmedRevision = pending.payload.interaction_revision;
          if (
            typeof record.cleanupInteractionRevision === "number"
            && confirmedRevision > record.cleanupInteractionRevision
          ) {
            return { state: "confirmed" };
          }
          return {
            state: "mismatch",
            reason: `${record.itemId} cleanup retry has not advanced past revision ${record.cleanupInteractionRevision ?? "?"}.`,
          };
        }
        if (pending.adapter === "image_ocr" || pending.adapter === "text_file") {
          return { state: "confirmed" };
        }
        return {
          state: "mismatch",
          reason: `${record.itemId} reached an invalid adapter after cleanup retry.`,
        };
      }
      return { state: "confirmed" };
    }

    // Every other cleanup action: confirmed only by a strictly higher
    // interaction_revision on the same still-pending cleanup item.
    if (pending !== null && pending.adapter === "cleanup" && pending.item_id === record.itemId) {
      const confirmedRevision = pending.payload.interaction_revision;
      if (
        typeof record.cleanupInteractionRevision === "number"
        && confirmedRevision > record.cleanupInteractionRevision
      ) {
        return { state: "confirmed" };
      }
      return {
        state: "mismatch",
        reason: `${record.itemId} cleanup interaction has not advanced past revision ${record.cleanupInteractionRevision ?? "?"}.`,
      };
    }
    // The item left the cleanup adapter without a Continue decision, or
    // disappeared outright — neither is this decision's expected outcome.
    return {
      state: "mismatch",
      reason: `${record.itemId} left the cleanup adapter unexpectedly.`,
    };
  }

  // Check 4 (every other adapter): the same decision must no longer be pending.
  if (view.pending && view.pending.item_id === record.itemId) {
    return {
      state: "mismatch",
      reason: `${record.itemId} is still awaiting a decision.`,
    };
  }

  return { state: "confirmed" };
}
