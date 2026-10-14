import { Sparkles } from "lucide-react";
import { useEffect } from "react";

import type { KnowledgeProposalPending, PhaseHandoffPending } from "../api/client";
import { AdapterFrame, Button } from "../components/primitives";
import type { AdapterProps } from "./types";

type GenericPending = PhaseHandoffPending | KnowledgeProposalPending;

/**
 * The fallback view for adapters without a purpose-built screen.
 *
 * It deliberately does not use ActionBar: it has no per-action descriptors and
 * renders whatever the coordinator returns, so no returned action can be
 * unsupported here. Stream 2 replaces it with real T19 and phase_handoff
 * screens built on ActionBar.
 */
export function GenericReview({
  pending,
  busy,
  submit,
  onUnsupported,
}: AdapterProps<GenericPending>) {
  // Every returned action is renderable here, so any contract failure raised by
  // a previously mounted adapter no longer applies.
  useEffect(() => onUnsupported(null), [onUnsupported]);

  return (
    <AdapterFrame
      title={pending.adapter === "phase_handoff"
        ? "Continue into knowledge work?"
        : "Review the knowledge proposal"}
      eyebrow={pending.adapter.replaceAll("_", " ")}
      icon={<Sparkles />}
    >
      <pre className="evidence-json">{JSON.stringify(pending.payload, null, 2)}</pre>
      <div className="actions">
        {pending.allowed_actions.map((action) => (
          <Button
            key={action}
            tone={action === "approve" || action === "continue"
              ? "primary"
              : action === "reject" ? "danger" : "quiet"}
            disabled={busy}
            onClick={() => submit(action, {})}
          >
            {action.replaceAll("_", " ")}
          </Button>
        ))}
      </div>
    </AdapterFrame>
  );
}
