import { AlertTriangle, ArrowLeft, ArrowRight, Check, Save, SkipForward, SpellCheck, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { CleanupPending } from "../api/client";
import { ActionBar, type ActionDescriptor } from "../components/ActionBar";
import { AdapterFrame, Metric } from "../components/primitives";
import type { AdapterProps } from "./types";

/** Every action the coordinator can offer that targets one occurrence. Used
 * to tell a real review state apart from the fallback-display state, where
 * the current phase found nothing and only Continue (if anything) applies. */
const PER_OCCURRENCE_ACTIONS = new Set([
  "apply_once", "apply_remember", "skip", "accept", "reject", "previous", "next",
]);

/** Mirrors _REPLACING_ACTIONS in text_cleanup/models.py: only these decisions
 * make proposed_text the occurrence's current, authoritative text. */
const REPLACING_DECISIONS = new Set(["apply_once", "apply_remember", "accept"]);

function isEditableTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element) return false;
  const tag = element.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || element.isContentEditable;
}

function exactMatches(text: string, shorthand: string, caseSensitive: boolean) {
  const needle = shorthand.trim();
  if (!needle) return [];
  const source = caseSensitive ? text : text.toLowerCase();
  const sought = caseSensitive ? needle : needle.toLowerCase();
  const matches: Array<{ start: number; context: string }> = [];
  let cursor = 0;
  while (cursor < source.length) {
    const start = source.indexOf(sought, cursor);
    if (start < 0) break;
    const end = start + needle.length;
    const leftOk = !needle[0]?.match(/[\p{L}\p{N}]/u)
      || start === 0
      || !text[start - 1]?.match(/[\p{L}\p{N}]/u);
    const rightOk = !needle.at(-1)?.match(/[\p{L}\p{N}]/u)
      || end === text.length
      || !text[end]?.match(/[\p{L}\p{N}]/u);
    if (leftOk && rightOk) {
      const before = text.slice(Math.max(0, start - 34), start);
      const after = text.slice(end, Math.min(text.length, end + 34));
      matches.push({ start, context: `${before}${text.slice(start, end)}${after}` });
    }
    cursor = start + 1;
  }
  return matches;
}

/**
 * Human-controlled abbreviation and spelling cleanup, inserted between
 * extraction and final content approval (component_8.md). Unlike every other
 * adapter, most actions here leave the same item pending on purpose (C8-C2):
 * one backend mutation per occurrence or navigation. Only Continue actually
 * finishes the gate.
 *
 * The abbreviation form previews every exact current-document match. Apply
 * once uses the human-entered expansion only for the visible occurrence;
 * Apply + remember makes that same edit and stores the mapping atomically for
 * later documents.
 */
export function CleanupReview({
  pending,
  busy,
  submit,
  onUnsupported,
}: AdapterProps<CleanupPending> & { token: string }) {
  const { payload } = pending;
  const occurrence = payload.state === "review" ? payload.occurrence : null;

  const isEmptyPhase = payload.state === "review"
    && !pending.allowed_actions.some((action) => PER_OCCURRENCE_ACTIONS.has(action));

  // Apply + remember's fields default from the current occurrence but stay
  // local until submitted (section 9.1) -- reset whenever the occurrence
  // changes so a stale edit can never attach to the wrong decision.
  const [rememberShorthand, setRememberShorthand] = useState(occurrence?.original_text ?? "");
  const [rememberExpansion, setRememberExpansion] = useState(occurrence?.proposed_text ?? "");
  const [rememberCaseSensitive, setRememberCaseSensitive] = useState(true);

  useEffect(() => {
    setRememberShorthand(occurrence?.original_text ?? "");
    setRememberExpansion(occurrence?.proposed_text ?? "");
    setRememberCaseSensitive(true);
  }, [occurrence?.occurrence_id]);

  // Keyed on the working text itself, not on `payload` -- `payload` is a
  // fresh object on every 750ms poll tick (useIngestion.ts) even when the
  // document hasn't changed, and this scan is O(document length). Keying on
  // the object reference re-ran the full scan every poll while this screen
  // sat open, on top of the (unavoidable) rerun on every keystroke in the
  // Shorthand field below -- the two together were the visible input lag.
  const workingText = payload.state === "review" ? payload.authoritative_working_text : null;
  const mappingMatches = useMemo(
    () => workingText !== null
      ? exactMatches(workingText, rememberShorthand, rememberCaseSensitive)
      : [],
    [workingText, rememberShorthand, rememberCaseSensitive],
  );
  const mappingMatchesVisibleOccurrence = occurrence !== null
    && rememberShorthand === occurrence.original_text;

  const revisionPayload = () => ({
    expected_interaction_revision: payload.interaction_revision,
  });
  const occurrencePayload = () => ({
    ...revisionPayload(),
    occurrence_id: occurrence?.occurrence_id ?? "",
    expected_working_draft_revision: payload.working_draft_revision,
  });

  const descriptors = useMemo<ActionDescriptor[]>(() => {
    if (payload.state === "unavailable") {
      return [
        { action: "retry", label: <>Retry <SpellCheck size={16} /></>, tone: "primary", buildPayload: () => ({}) },
      ];
    }
    return [
      {
        action: "apply_once",
        label: <>Apply once <Check size={17} /><kbd>Enter</kbd></>,
        tone: "primary",
        disabled: !mappingMatchesVisibleOccurrence || !rememberExpansion.trim(),
        buildPayload: () => ({
          ...occurrencePayload(),
          shorthand: rememberShorthand,
          expansion: rememberExpansion,
          case_sensitive: rememberCaseSensitive,
        }),
      },
      {
        action: "apply_remember",
        label: <>Apply + remember <Save size={16} /></>,
        disabled: !mappingMatchesVisibleOccurrence || !rememberExpansion.trim(),
        buildPayload: () => ({
          ...occurrencePayload(),
          shorthand: rememberShorthand,
          expansion: rememberExpansion,
          case_sensitive: rememberCaseSensitive,
        }),
      },
      {
        action: "skip",
        label: <>Skip <SkipForward size={16} /><kbd>Backspace</kbd></>,
        buildPayload: occurrencePayload,
      },
      {
        action: "accept",
        label: <>Accept <Check size={17} /><kbd>Enter</kbd></>,
        tone: "primary",
        buildPayload: occurrencePayload,
      },
      {
        action: "reject",
        label: <>Reject <X size={16} /><kbd>Backspace</kbd></>,
        buildPayload: occurrencePayload,
      },
      {
        action: "previous",
        label: <>Previous <ArrowLeft size={16} /><kbd>&larr;</kbd></>,
        buildPayload: occurrencePayload,
      },
      {
        action: "next",
        label: <>Next <ArrowRight size={16} /><kbd>&rarr;</kbd></>,
        buildPayload: occurrencePayload,
      },
      {
        action: "continue",
        label: <>Continue to approval <ArrowRight size={17} /></>,
        tone: "primary",
        buildPayload: () => ({
          expected_interaction_revision: payload.interaction_revision,
          expected_working_draft_revision: payload.working_draft_revision,
        }),
      },
    ];
  }, [occurrence, payload, rememberShorthand, rememberExpansion, rememberCaseSensitive, mappingMatchesVisibleOccurrence]);

  // C8-C6: Right/Left navigate, Enter is the phase's primary decision, and
  // Backspace is its secondary one. Apply + remember and Continue stay
  // button-only because both have side effects. Shift+Enter stays reserved
  // for the existing final image/highlight approval and is never intercepted
  // here.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (busy || payload.state !== "review" || isEditableTarget(event.target)) return;
      let action: string | null = null;
      if (event.key === "ArrowRight") action = "next";
      else if (event.key === "ArrowLeft") action = "previous";
      else if (event.key === "Enter" && !event.shiftKey) {
        action = payload.phase === "abbreviation" ? "apply_once" : "accept";
      } else if (event.key === "Backspace") {
        action = payload.phase === "abbreviation" ? "skip" : "reject";
      }
      if (!action || !pending.allowed_actions.includes(action)) return;
      const descriptor = descriptors.find((item) => item.action === action);
      if (!descriptor || descriptor.disabled) return;
      event.preventDefault();
      submit(action, descriptor.buildPayload());
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [busy, descriptors, payload, pending.allowed_actions, submit]);

  const phaseLabel = payload.state === "review" && payload.phase === "spelling" ? "Spelling" : "Abbreviation";

  return (
    <AdapterFrame
      title={payload.state === "unavailable" ? "Spelling checker unavailable" : `${phaseLabel} review`}
      eyebrow="Text cleanup · before final approval"
      icon={payload.state === "unavailable" ? <AlertTriangle /> : <SpellCheck />}
      aside={
        <>
          {payload.state === "review" && (
            <Metric label="Occurrence" value={occurrence ? `${occurrence.ordinal} of ${occurrence.total}` : "—"} />
          )}
          <Metric label="Phase" value={payload.state === "review" ? phaseLabel : "Spelling"} />
          <Metric label="Source" value={payload.source_kind} />
        </>
      }
    >
      {payload.state === "unavailable" ? (
        <div className="error-banner">
          <AlertTriangle size={18} />
          <span>{payload.error}</span>
        </div>
      ) : isEmptyPhase ? (
        <p className="slug">
          No further {payload.phase} suggestions were found. The passage below reflects the last
          decision made.
        </p>
      ) : null}

      {payload.state === "review" && occurrence && (
        <>
          <p className="highlight-text" role="status" aria-live="polite">
            {occurrence.context_before}
            <mark>
              {occurrence.current_decision && REPLACING_DECISIONS.has(occurrence.current_decision)
                ? occurrence.proposed_text
                : occurrence.original_text}
            </mark>
            {occurrence.context_after}
          </p>
          {!isEmptyPhase && (
            <div className="slug">
              {occurrence.current_decision && REPLACING_DECISIONS.has(occurrence.current_decision)
                ? <>Applied: <code>{occurrence.proposed_text}</code></>
                : <>Proposed: <code>{occurrence.proposed_text}</code></>}
              {occurrence.current_decision && (
                <> — currently <strong>{occurrence.current_decision}</strong></>
              )}
            </div>
          )}
        </>
      )}

      {payload.state === "review" && payload.phase === "abbreviation" && !isEmptyPhase && (
        <fieldset className="edit-grid">
          <label>
            Shorthand
            <input value={rememberShorthand} onChange={(event) => setRememberShorthand(event.target.value)} />
          </label>
          <label>
            Expansion
            <input value={rememberExpansion} onChange={(event) => setRememberExpansion(event.target.value)} />
          </label>
          <label>
            <input
              type="checkbox"
              checked={rememberCaseSensitive}
              onChange={(event) => setRememberCaseSensitive(event.target.checked)}
            />
            {" "}Case sensitive
          </label>
          <p className="diag-empty">
            {mappingMatchesVisibleOccurrence
              ? `${mappingMatches.length} exact ${mappingMatches.length === 1 ? "match" : "matches"} in this document. Apply once changes only the highlighted occurrence; Apply + remember also saves the mapping.`
              : "The shorthand must exactly match the highlighted occurrence."}
          </p>
          {mappingMatchesVisibleOccurrence && mappingMatches.length > 0 && (
            <ul className="diag-list" aria-label="Exact shorthand matches in this document">
              {mappingMatches.map((match) => (
                <li key={`${rememberShorthand}-${match.start}`}><code>{match.context}</code></li>
              ))}
            </ul>
          )}
        </fieldset>
      )}

      <ActionBar
        adapter="cleanup"
        allowedActions={pending.allowed_actions}
        descriptors={descriptors}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    </AdapterFrame>
  );
}
