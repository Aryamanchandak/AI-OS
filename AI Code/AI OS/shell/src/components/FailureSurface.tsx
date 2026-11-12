import { AlertTriangle } from "lucide-react";

import type { Failure } from "../failures";

export const FAILURE_SURFACE_ID = "failure-surface";

/**
 * The one prominent failure surface.
 *
 * Failures from different layers are rendered side by side and never merged:
 * a background operation error and a coordinator stage error describe
 * different things, and either may hold the useful failure point. The exact
 * backend message is always shown; the heading is additive, not a replacement.
 */
export function FailureSurface({
  failures,
  actions,
}: {
  failures: Failure[];
  actions?: React.ReactNode;
}) {
  if (failures.length === 0) return null;
  return (
    <section
      id={FAILURE_SURFACE_ID}
      className="failure-surface"
      // Focusable so a keyboard user can deliberately move here from the status
      // line. Never focused programmatically: polling must not move the caret
      // out from under the user.
      tabIndex={-1}
      aria-label="Failure details"
    >
      {failures.map((failure) => (
        <article className={`failure failure-${failure.layer}`} key={failure.identity}>
          <header>
            <AlertTriangle size={18} aria-hidden="true" />
            <h2>{failure.heading}</h2>
          </header>
          <p className="failure-message">{failure.message}</p>
          <dl className="failure-facts">
            {failure.facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
      {actions && <div className="failure-actions">{actions}</div>}
    </section>
  );
}

/**
 * Announces a newly arrived failure exactly once.
 *
 * The visual surface above re-renders on every 750ms poll. Putting the live
 * region there would re-announce the same failure continuously, so the
 * announcement lives in its own node whose content changes only when the
 * failure identity does.
 */
export function FailureAnnouncer({ failures }: { failures: Failure[] }) {
  // Keyed on the stable failure identity — layer, run, operation/stage,
  // revision and message. An unchanged identity keeps the same node, so
  // repeated polls of one failure are not re-announced; a changed identity
  // mounts a fresh alert, so a genuinely new failure is announced even when its
  // text happens to read the same as the last one.
  const identity = failures.map((failure) => failure.identity).join(" · ");
  const message = failures
    .map((failure) => `${failure.heading}. ${failure.message}`)
    .join(" ");

  return (
    <p
      key={identity}
      role="alert"
      className="visually-hidden"
      data-testid="failure-announcer"
    >
      {message}
    </p>
  );
}
