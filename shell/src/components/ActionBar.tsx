import { useEffect, type ReactNode } from "react";

import { Button } from "./primitives";

/**
 * An adapter's description of one server mutation it knows how to submit.
 *
 * The adapter owns the label, tone, icon, validation and payload; the bar owns
 * only the rule that an action is rendered if and only if the coordinator
 * returned it in allowed_actions.
 */
export type ActionDescriptor = {
  action: string;
  label: ReactNode;
  tone?: "primary" | "quiet" | "danger";
  /** Extra reason this action cannot be submitted right now, beyond busy. */
  disabled?: boolean;
  buildPayload: () => Record<string, unknown>;
};

export type UnsupportedActions = {
  adapter: string;
  actions: string[];
};

/**
 * Compare what the coordinator allows against what the adapter can serialize.
 *
 * Order is the adapter's, so the buttons do not reshuffle when the coordinator
 * returns its actions in a different order.
 */
export function resolveActions(
  allowed: readonly string[],
  descriptors: readonly ActionDescriptor[],
): { rendered: ActionDescriptor[]; unsupported: string[] } {
  const known = new Set(descriptors.map((descriptor) => descriptor.action));
  return {
    rendered: descriptors.filter((descriptor) => allowed.includes(descriptor.action)),
    unsupported: allowed.filter((action) => !known.has(action)),
  };
}

/**
 * Renders only coordinator-returned legal actions.
 *
 * If the coordinator returns an action this adapter has no descriptor for, the
 * view fails loudly instead of quietly dropping a button: mutation submission
 * is disabled and the caller surfaces an "Unsupported action contract" error.
 * Local controls that never call the server (Edit fields, Cancel editing) stay
 * outside this bar.
 */
export function ActionBar({
  adapter,
  allowedActions,
  descriptors,
  busy,
  submit,
  onUnsupported,
  children,
}: {
  adapter: string;
  allowedActions: readonly string[];
  descriptors: readonly ActionDescriptor[];
  busy: boolean;
  submit: (action: string, payload: Record<string, unknown>) => void;
  onUnsupported: (unsupported: UnsupportedActions | null) => void;
  /** Local, non-server controls rendered alongside the legal server actions. */
  children?: ReactNode;
}) {
  const { rendered, unsupported } = resolveActions(allowedActions, descriptors);
  const blocked = unsupported.length > 0;
  const signature = unsupported.join(",");

  // Reported from an effect, keyed on the unsupported set itself, so a 750ms
  // poll does not re-raise the same contract failure on every render.
  useEffect(() => {
    onUnsupported(signature ? { adapter, actions: signature.split(",") } : null);
  }, [adapter, signature, onUnsupported]);

  return (
    <div className="actions">
      {rendered.map((descriptor) => (
        <Button
          key={descriptor.action}
          tone={descriptor.tone ?? "quiet"}
          disabled={busy || blocked || descriptor.disabled === true}
          onClick={() => submit(descriptor.action, descriptor.buildPayload())}
        >
          {descriptor.label}
        </Button>
      ))}
      {children}
    </div>
  );
}
