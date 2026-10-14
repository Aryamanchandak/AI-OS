import { isValidConfirmation, type PendingConfirmation } from "./settlement";
import { DRAFT_PREFIX } from "./storage";

/**
 * Safe local edits, keyed by run and item so one run's draft can never be
 * applied to a different item. The accepted-but-unsettled submission is stored
 * with the draft, so a refresh can reconcile it instead of losing its identity.
 *
 * `value` is null when a decision was submitted for an item that keeps no
 * editable draft — the submission still needs recording.
 */
export type DraftRecord<T> = {
  value: T | null;
  pending: PendingConfirmation | null;
};

export type DraftRead<T> =
  | { status: "empty" }
  | { status: "ok"; record: DraftRecord<T> }
  /** Storage existed but could not be trusted. The caller shows this, then
   *  falls back to backend truth. It is never sent to the server. */
  | { status: "corrupt"; reason: string };

export function draftKey(runId: string, itemId: string): string {
  return `${DRAFT_PREFIX}${runId}:${itemId}`;
}

function readRaw(runId: string, itemId: string): Record<string, unknown> | null {
  try {
    const raw = sessionStorage.getItem(draftKey(runId, itemId));
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return null;
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function readDraft<T>(
  runId: string,
  itemId: string,
  isValidValue: (value: unknown) => value is T,
): DraftRead<T> {
  let raw: string | null;
  try {
    raw = sessionStorage.getItem(draftKey(runId, itemId));
  } catch {
    return { status: "corrupt", reason: "Local session storage is unavailable." };
  }
  if (raw === null) return { status: "empty" };

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { status: "corrupt", reason: "The saved draft is not readable JSON." };
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { status: "corrupt", reason: "The saved draft is not a draft record." };
  }

  const record = parsed as Record<string, unknown>;
  const pending = record.pending;
  if (pending !== null && pending !== undefined && !isValidConfirmation(pending)) {
    return { status: "corrupt", reason: "The saved submission record is incomplete." };
  }
  const confirmation = isValidConfirmation(pending) ? pending : null;

  // A record may legitimately carry only a submission marker.
  if (record.value === null || record.value === undefined) {
    return { status: "ok", record: { value: null, pending: confirmation } };
  }
  // Shape, not just parseability: valid JSON of the wrong shape would otherwise
  // survive to the render that maps over it.
  if (!isValidValue(record.value)) {
    return { status: "corrupt", reason: "The saved draft does not match this item." };
  }
  return { status: "ok", record: { value: record.value, pending: confirmation } };
}

export function writeDraft<T>(
  runId: string,
  itemId: string,
  record: DraftRecord<T>,
): void {
  try {
    sessionStorage.setItem(draftKey(runId, itemId), JSON.stringify(record));
  } catch {
    // A full or disabled session store must not take the review screen down.
    // The draft is a convenience; backend truth is unaffected.
  }
}

/**
 * Clear exactly one draft, after its own decision was confirmed. Orphaned
 * drafts from other runs are deliberately left in place — this stream does not
 * bulk-delete work the user may still want.
 */
export function clearDraft(runId: string, itemId: string): void {
  try {
    sessionStorage.removeItem(draftKey(runId, itemId));
  } catch {
    // Nothing to recover: the draft is already unreachable.
  }
}

/** Record an accepted-but-unsettled submission alongside any existing draft. */
export function markSubmitted(
  runId: string,
  itemId: string,
  pending: PendingConfirmation,
): void {
  const existing = readRaw(runId, itemId);
  writeDraft(runId, itemId, {
    // Kept verbatim and unvalidated: validation belongs where it is displayed.
    value: (existing?.value ?? null) as unknown,
    pending,
  });
}

/**
 * Find an accepted-but-unsettled submission for this run after a refresh.
 *
 * The pending item may have moved on while the page was gone, so the run's own
 * draft keys are scanned rather than assuming the outstanding submission
 * belongs to whatever is pending now. Only this run's keys are read; other
 * runs' drafts are left untouched.
 */
export function findOutstandingSubmission(runId: string): PendingConfirmation | null {
  const prefix = `${DRAFT_PREFIX}${runId}:`;
  let keys: string[];
  try {
    keys = Object.keys(sessionStorage).filter((key) => key.startsWith(prefix));
  } catch {
    return null;
  }
  for (const key of keys) {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(key) ?? "") as unknown;
      if (typeof parsed !== "object" || parsed === null) continue;
      const pending = (parsed as Record<string, unknown>).pending;
      if (isValidConfirmation(pending) && pending.runId === runId) return pending;
    } catch {
      // A corrupt entry is reported by readDraft when its item is displayed.
      continue;
    }
  }
  return null;
}

/**
 * Forget an accepted submission whose outcome is now known, keeping the draft
 * itself. Without this a settled-but-unsuccessful decision would be adopted
 * again on the next poll.
 */
export function clearSubmission(runId: string, itemId: string): void {
  const existing = readRaw(runId, itemId);
  if (existing === null || existing.pending === null || existing.pending === undefined) return;
  writeDraft(runId, itemId, { value: (existing.value ?? null) as unknown, pending: null });
}
