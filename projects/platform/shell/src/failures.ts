import { ApiError, type Snapshot } from "./api/client";

/**
 * The layers a failure can come from. They are never merged: a request that was
 * accepted with 202 and then failed inside the coordinator produces both a
 * service-operation error and a coordinator error, and either one may hold the
 * useful failure point.
 */
export type FailureLayer =
  | "transport"
  | "operation"
  | "coordinator"
  | "contract"
  | "draft";

export type Failure = {
  layer: FailureLayer;
  heading: string;
  /** The exact backend text. Never replaced with a friendly substitute. */
  message: string;
  facts: { label: string; value: string }[];
  /** Present only when the coordinator itself says a retry is legal. */
  retryable: boolean;
  /** Stable identity used to announce a failure once, across many polls. */
  identity: string;
  /** HTTP status, when this failure came from a response. 0 for no response. */
  status?: number;
};

const NONE = "not reported";

function identityOf(parts: (string | number | boolean | null | undefined)[]): string {
  return parts.map((part) => (part === null || part === undefined ? "" : String(part))).join("|");
}

/** Transport, auth and HTTP failures — the request never produced backend truth. */
export function transportFailure(cause: unknown): Failure {
  const error = cause instanceof ApiError ? cause : null;
  const message = error
    ? error.message
    : cause instanceof Error
      ? cause.message
      : "The gateway did not answer.";
  const status = error ? error.status : 0;
  const name = error ? error.request : "Request";
  return {
    layer: "transport",
    heading: `${name} could not be completed`,
    message,
    facts: [
      { label: "Request", value: name },
      { label: "Status", value: status === 0 ? "no response" : String(status) },
    ],
    retryable: false,
    identity: identityOf(["transport", name, status, message]),
    status,
  };
}

/**
 * A call the gateway accepted with 202 that later settled as failed. The
 * coordinator never ran to completion, so there may be no view-level error at
 * all — this is the only place that failure is visible.
 */
export function operationFailure(snapshot: Snapshot | null): Failure | null {
  if (!snapshot || snapshot.operation.state !== "failed") return null;
  const operation = snapshot.operation.name ?? "The background operation";
  const message = snapshot.operation.error ?? "The service reported no message.";
  return {
    layer: "operation",
    heading: `${operation} failed`,
    message,
    facts: [
      { label: "Operation", value: snapshot.operation.name ?? NONE },
      { label: "Revision", value: String(snapshot.operation.revision) },
      { label: "Run", value: snapshot.view?.run_id ?? NONE },
    ],
    // Whether a retry is legal is the coordinator's call, never this layer's.
    retryable: false,
    identity: identityOf([
      "operation",
      snapshot.view?.run_id,
      snapshot.operation.name,
      snapshot.operation.revision,
      message,
    ]),
  };
}

/** A stage the coordinator itself reported as failed, with its retry verdict. */
export function coordinatorFailure(snapshot: Snapshot | null): Failure | null {
  const view = snapshot?.view;
  const lastError = view?.last_error;
  if (!view || !lastError) return null;
  return {
    layer: "coordinator",
    heading: `${lastError.stage} failed`,
    message: lastError.message,
    facts: [
      { label: "Stage", value: lastError.stage },
      { label: "Stage status", value: view.stage_status },
      { label: "Run", value: view.run_id },
      { label: "Retryable", value: lastError.retryable ? "yes" : "no" },
    ],
    retryable: lastError.retryable,
    identity: identityOf([
      "coordinator",
      view.run_id,
      lastError.stage,
      snapshot?.operation.revision,
      lastError.message,
    ]),
  };
}

/**
 * The coordinator returned a legal action this adapter cannot serialize. It is
 * shown rather than silently dropped: a missing button is indistinguishable
 * from an action the backend never offered.
 */
export function contractFailure(adapter: string, actions: string[]): Failure {
  const listed = actions.join(", ");
  return {
    layer: "contract",
    heading: "Unsupported action contract",
    message:
      `The coordinator returned ${actions.length === 1 ? "an action" : "actions"} `
      + `the ${adapter} view cannot submit: ${listed}.`,
    facts: [
      { label: "Adapter", value: adapter },
      { label: "Unsupported actions", value: listed },
    ],
    retryable: false,
    identity: identityOf(["contract", adapter, listed]),
  };
}

/** Local draft storage that could not be trusted. */
export function draftFailure(runId: string, itemId: string, reason: string): Failure {
  return {
    layer: "draft",
    heading: "Saved local edits could not be restored",
    message: reason,
    facts: [
      { label: "Run", value: runId },
      { label: "Item", value: itemId },
    ],
    retryable: false,
    identity: identityOf(["draft", runId, itemId, reason]),
  };
}
