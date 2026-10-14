import { ArrowRight, ListChecks, Square } from "lucide-react";
import { useMemo } from "react";

import type { PhaseHandoffPending } from "../api/client";
import { ActionBar, type ActionDescriptor } from "../components/ActionBar";
import { AdapterFrame, Metric } from "../components/primitives";
import type { AdapterProps } from "./types";

/**
 * The presentation-only run-level gate at the intake/knowledge boundary. The
 * gate itself needs no payload (gates.py:302-322): Continue and Stop both
 * submit `{}`. `pending.item_id` is the coordinator's canonical empty string
 * for a run-level decision (gates.py:315), never a missing item — it is used
 * as-is for the `key` prop and never guarded against.
 */
export function PhaseHandoffReview({
  pending,
  busy,
  submit,
  onUnsupported,
}: AdapterProps<PhaseHandoffPending>) {
  const { payload } = pending;

  const descriptors = useMemo<ActionDescriptor[]>(() => [
    {
      action: "continue",
      label: <>Continue into knowledge work <ArrowRight size={17} /></>,
      tone: "primary",
      buildPayload: () => ({}),
    },
    {
      action: "stop",
      label: <>Stop — complete the run <Square size={15} /></>,
      tone: "danger",
      buildPayload: () => ({}),
    },
  ], []);

  return (
    <AdapterFrame
      title="Continue into knowledge work?"
      eyebrow="Intake complete"
      icon={<ListChecks />}
      aside={
        <>
          <Metric label="Discovered" value={payload.discovered} />
          <Metric label="Published" value={payload.published} />
          <Metric label="Discarded" value={payload.discarded} />
          <Metric label="Retake" value={payload.retake} />
          <Metric label="Duplicate" value={payload.duplicate} />
          <Metric label="Failed" value={payload.failed} />
        </>
      }
    >
      <p className="diag-empty">
        Stop completes this run — it does not pause it. Nothing captured so far is discarded, but no
        further items will be processed once the run stops.
      </p>
      <p className="eyebrow">Notes written to the vault</p>
      {payload.note_paths.length === 0 ? (
        <p className="diag-empty">none</p>
      ) : (
        <ul className="diag-list">
          {payload.note_paths.map((path) => <li key={path}>{path}</li>)}
        </ul>
      )}
      <ActionBar
        adapter="phase_handoff"
        allowedActions={pending.allowed_actions}
        descriptors={descriptors}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    </AdapterFrame>
  );
}
