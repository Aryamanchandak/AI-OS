import type { Pending } from "../api/client";
import type { UnsupportedActions } from "../components/ActionBar";

/**
 * Submit a server mutation. There is deliberately no "accepted" callback: a
 * 202 means accepted for processing, and nothing may be cleared or celebrated
 * from it. Settlement is decided centrally against a later snapshot.
 */
export type SubmitDecision = (
  action: string,
  payload: Record<string, unknown>,
) => void;

export type AdapterProps<P extends Pending> = {
  pending: P;
  busy: boolean;
  submit: SubmitDecision;
  /** Raised when the coordinator returns an action this adapter cannot submit. */
  onUnsupported: (unsupported: UnsupportedActions | null) => void;
};
