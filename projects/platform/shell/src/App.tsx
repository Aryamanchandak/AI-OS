import { AnimatePresence } from "framer-motion";
import { Check, KeyRound, Play, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type Decision } from "./api/client";
import { ActionBar, type UnsupportedActions } from "./components/ActionBar";
import { AppShell } from "./components/AppShell";
import { EnvelopeFlight } from "./components/EnvelopeFlight";
import {
  FAILURE_SURFACE_ID,
  FailureAnnouncer,
  FailureSurface,
} from "./components/FailureSurface";
import { Button } from "./components/primitives";
import { RunDiagnostics } from "./components/RunDiagnostics";
import { TokenGate } from "./components/TokenGate";
import {
  clearDraft,
  clearSubmission,
  findOutstandingSubmission,
  markSubmitted,
} from "./drafts";
import { contractFailure, transportFailure, type Failure } from "./failures";
import { useIngestion } from "./hooks/useIngestion";
import { BookReview } from "./screens/BookReview";
import { CleanupReview } from "./screens/CleanupReview";
import { GenericReview } from "./screens/GenericReview";
import { ImageReview } from "./screens/ImageReview";
import { KnowledgeProposalReview } from "./screens/KnowledgeProposalReview";
import { PhaseHandoffReview } from "./screens/PhaseHandoffReview";
import { TextReview } from "./screens/TextReview";
import { settle, type PendingConfirmation } from "./settlement";
import { TOKEN_KEY } from "./storage";
import { ChannelsAdmin } from "./screens/ChannelsAdmin";
import { Help } from "./screens/Help";
import { LLMDashboard } from "./screens/LLMDashboard";
import { Observability } from "./screens/Observability";

export default function App() {
  const { pathname } = window.location;
  if (pathname === "/channels") return <ChannelsAdmin />;
  if (pathname === "/llm") return <LLMDashboard />;
  if (pathname === "/observability") return <Observability />;
  if (pathname === "/help") return <Help />;
  return <IngestionApp />;
}

function IngestionApp() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const {
    snapshot,
    loading,
    transportFailure: pollFailure,
    operationFailure,
    coordinatorFailure,
    reportFailure,
    report,
    startFailed,
    unauthorized,
    refresh,
    reconnect,
    startAgain,
    retry,
  } = useIngestion(token);

  const [celebrate, setCelebrate] = useState(false);
  const [submitFailure, setSubmitFailure] = useState<Failure | null>(null);
  const [unsupported, setUnsupported] = useState<UnsupportedActions | null>(null);
  const [draftProblem, setDraftProblem] = useState<Failure | null>(null);
  const [pendingConfirmation, setPendingConfirmation] =
    useState<PendingConfirmation | null>(null);
  const [draftState, setDraftState] = useState<string | null>(null);
  const [retryHistory, setRetryHistory] = useState<string[]>([]);
  // "requesting" covers the in-flight POST; only once the gateway accepts it
  // does an incoming snapshot describe the retry's own outcome.
  const [retryPhase, setRetryPhase] = useState<"idle" | "requesting" | "awaiting">("idle");

  const view = snapshot?.view;
  const pending = view?.pending;
  const busy = snapshot?.operation.state === "submitting";
  const revision = snapshot?.operation.revision ?? 0;

  // ---- Settlement -------------------------------------------------------
  // A 202 only records what was submitted. Every success indicator below waits
  // for a later snapshot to confirm that exact decision.

  useEffect(() => {
    if (!pendingConfirmation) return;
    const outcome = settle(pendingConfirmation, snapshot ?? null);
    if (outcome.state === "waiting") return;

    const { runId, itemId, adapter, action } = pendingConfirmation;
    if (outcome.state === "confirmed") {
      clearDraft(runId, itemId);
      setDraftState(`Draft cleared after confirmed success (${action} on ${itemId}).`);
      // Check 1: only an approved image highlight earns the envelope.
      if (adapter === "image_ocr" && action === "approve") setCelebrate(true);
    } else {
      // Retained on failure, mismatch, 409, 412, transport error and refresh.
      clearSubmission(runId, itemId);
      setDraftState(`Draft retained — ${outcome.reason}`);
    }
    setPendingConfirmation(null);
  }, [pendingConfirmation, snapshot]);

  // Recover an accepted-but-unsettled submission after a refresh or reconnect,
  // so its identity is reconciled rather than lost.
  useEffect(() => {
    if (pendingConfirmation || !view?.run_id) return;
    const outstanding = findOutstandingSubmission(view.run_id);
    if (outstanding) setPendingConfirmation(outstanding);
  }, [pendingConfirmation, view?.run_id]);

  // A settled retry stops the waiting state and is recorded as a durable fact.
  useEffect(() => {
    if (retryPhase !== "awaiting" || !snapshot) return;
    if (snapshot.operation.state === "submitting") return;
    setRetryPhase("idle");
    setRetryHistory((entries) => [
      ...entries,
      snapshot.operation.state === "failed"
        ? `Retry failed at revision ${snapshot.operation.revision}: ${snapshot.operation.error}`
        : snapshot.view?.last_error
          ? `Retry did not clear ${snapshot.view.last_error.stage}: ${snapshot.view.last_error.message}`
          : `Retry confirmed succeeded at revision ${snapshot.operation.revision}.`,
    ]);
  }, [retryPhase, snapshot]);

  const submit = useCallback(async (
    action: string,
    payload: Record<string, unknown>,
  ) => {
    if (!snapshot || !view?.pending) return;
    const target = view.pending;
    const body: Decision = {
      run_id: view.run_id,
      item_id: target.item_id,
      gate: target.gate,
      action,
      payload,
      expected_revision: snapshot.operation.revision,
    };
    const record: PendingConfirmation = {
      runId: view.run_id,
      itemId: target.item_id,
      adapter: target.adapter,
      action,
      submittedRevision: snapshot.operation.revision,
      // Cleanup's same-item confirmation rule (C8-C2, settlement.ts) needs the
      // interaction_revision this decision was submitted against.
      ...(target.adapter === "cleanup"
        ? { cleanupInteractionRevision: target.payload.interaction_revision }
        : {}),
    };
    try {
      await api.decide(token, body);
      setSubmitFailure(null);
      // Accepted for processing. Nothing is cleared and nothing celebrates yet.
      setPendingConfirmation(record);
      markSubmitted(record.runId, record.itemId, record);
      setDraftState(`Draft retained — ${action} on ${target.item_id} accepted, awaiting confirmation.`);
      await refresh();
    } catch (cause) {
      // The submission was rejected outright, so no confirmation record exists
      // and no later unrelated success can be mistaken for this one.
      setPendingConfirmation(null);
      setSubmitFailure(transportFailure(cause));
      setDraftState("Draft retained — the submission was rejected.");
      // 412 means the shell was stale: show current backend truth instead.
      await refresh();
    }
  }, [refresh, snapshot, token, view]);

  const onRetry = useCallback(async () => {
    setRetryPhase("requesting");
    const accepted = await retry();
    setRetryPhase(accepted ? "awaiting" : "idle");
  }, [retry]);

  const handleUnsupported = useCallback((next: UnsupportedActions | null) => {
    setUnsupported(next);
  }, []);

  const handleDraftProblem = useCallback((next: Failure | null) => {
    setDraftProblem(next);
  }, []);

  const contractError = useMemo(
    () => (unsupported ? contractFailure(unsupported.adapter, unsupported.actions) : null),
    [unsupported],
  );

  // Every layer is shown; none replaces another.
  const failures = useMemo(
    () => [
      pollFailure,
      submitFailure,
      operationFailure,
      coordinatorFailure,
      contractError,
      draftProblem,
      reportFailure,
    ].filter((failure): failure is Failure => failure !== null),
    [
      coordinatorFailure,
      contractError,
      draftProblem,
      operationFailure,
      pollFailure,
      reportFailure,
      submitFailure,
    ],
  );

  const canRetry = coordinatorFailure?.retryable === true;
  const retryBusy = retryPhase !== "idle";
  // Cleanup's same-item confirmation (C8-C2) means the same screen, same
  // item, and same buttons can still be on screen in the gap between the
  // operation going idle and the confirming poll landing -- unlike every
  // other adapter, where the item itself is gone by then. Block mutations
  // through that gap too, or a second submit races the first decision's own
  // settlement (section 9.1: "disables duplicate mutations ... while
  // settlement is pending").
  const mutationsBlocked = busy === true || retryBusy || contractError !== null || pendingConfirmation !== null;

  const lock = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken("");
  }, []);

  if (!token) return <TokenGate onUnlock={setToken} />;

  const statusText = retryBusy
    ? "Retry accepted; waiting for confirmation"
    : busy
      ? "Accepted for processing"
      : failures.length > 0
        ? "Attention needed"
        : pending
          ? "Waiting for your decision"
          : view?.terminal_result === "complete"
            ? "Run complete"
            : view?.terminal_result === "failed"
              ? "Run failed"
              : "Connecting";

  return (
    <AppShell onLock={lock} active="ingestion">
      <div className="runline">
        <div>
          <span className={`pulse ${busy || retryBusy ? "working" : ""}`} />
          {statusText}
          {failures.length > 0 && (
            // Keyboard users reach the surface deliberately; nothing steals focus.
            <a className="failure-jump" href={`#${FAILURE_SURFACE_ID}`}>
              Go to failure details
            </a>
          )}
        </div>
        <div>
          {view?.run_id && <code>{view.run_id}</code>}
          <span>rev {revision}</span>
        </div>
      </div>

      <FailureAnnouncer failures={failures} />

      <FailureSurface
        failures={failures}
        actions={
          <>
            {canRetry && (
              <Button tone="primary" disabled={retryBusy || busy} onClick={() => void onRetry()}>
                <RotateCcw size={16} /> Retry
              </Button>
            )}
            {startFailed && (
              <Button tone="primary" disabled={busy} onClick={() => void startAgain()}>
                <Play size={16} /> Try start again
              </Button>
            )}
            {pollFailure && unauthorized ? (
              // A 401 will not clear by re-polling with the same token — the
              // token itself is wrong. Send the user back to the token screen
              // instead of a Reconnect that would just repeat the same 401.
              <Button tone="primary" onClick={lock}>
                <KeyRound size={16} /> Re-enter key
              </Button>
            ) : (
              pollFailure && (
                // Re-polls only. It never retries a stage and never resubmits
                // a decision.
                <Button onClick={() => void reconnect()}>
                  <RotateCcw size={16} /> Reconnect
                </Button>
              )
            )}
          </>
        }
      />

      {loading && !snapshot ? (
        <div className="loading-state">
          <span className="orb" />
          <p>Finding the current durable work…</p>
        </div>
      ) : startFailed ? (
        <section className="loading-state">
          <p>The ingestion run did not start. The exact failure is shown above.</p>
        </section>
      ) : !view ? (
        <div className="loading-state">
          <span className="orb" />
          <p>Starting the ingestion run…</p>
        </div>
      ) : pending ? (
        <AnimatePresence mode="wait">
          {pending.adapter === "book_identity" ? (
            <BookReview
              key={pending.item_id}
              pending={pending}
              busy={mutationsBlocked}
              submit={submit}
              onUnsupported={handleUnsupported}
            />
          ) : pending.adapter === "image_ocr" ? (
            <ImageReview
              key={pending.item_id}
              pending={pending}
              busy={mutationsBlocked}
              submit={submit}
              onUnsupported={handleUnsupported}
              onDraftProblem={handleDraftProblem}
              token={token}
              runId={view.run_id}
            />
          ) : pending.adapter === "text_file" ? (
            <TextReview
              key={pending.item_id}
              pending={pending}
              busy={mutationsBlocked}
              submit={submit}
              onUnsupported={handleUnsupported}
            />
          ) : pending.adapter === "phase_handoff" ? (
            <PhaseHandoffReview
              key={pending.item_id}
              pending={pending}
              busy={mutationsBlocked}
              submit={submit}
              onUnsupported={handleUnsupported}
            />
          ) : pending.adapter === "knowledge_proposal" ? (
            // Keyed on the envelope, not the individual proposal: every
            // proposal derived from one highlight (claim, concepts,
            // relations) stays on the same mounted screen instance so the
            // shared highlight/evidence chrome renders once instead of
            // remounting -- and re-reading the same sentence -- once per
            // proposal. KnowledgeProposalReview itself still keys each
            // proposal's own edit form so per-proposal local state (an
            // in-progress edit) never bleeds into the next proposal.
            <KnowledgeProposalReview
              key={(pending.payload as { envelope_id?: string }).envelope_id ?? pending.item_id}
              pending={pending}
              busy={mutationsBlocked}
              submit={submit}
              onUnsupported={handleUnsupported}
              token={token}
              runId={view.run_id}
            />
          ) : pending.adapter === "cleanup" ? (
            <CleanupReview
              key={pending.item_id}
              pending={pending}
              busy={mutationsBlocked}
              submit={submit}
              onUnsupported={handleUnsupported}
              token={token}
            />
          ) : (
            // `pending` is provably `never` here now that every union member has
            // its own branch above (see App.tsx dispatch note in Workstream 2).
            // The cast is only for the `key` expression — GenericReview's own
            // prop type is left exactly as it was, deliberately not widened.
            <GenericReview
              key={(pending as { item_id: string }).item_id}
              pending={pending}
              busy={mutationsBlocked}
              submit={submit}
              onUnsupported={handleUnsupported}
            />
          )}
        </AnimatePresence>
      ) : view.terminal_result === "complete" && failures.length === 0 ? (
        <section className="complete">
          <div className="complete-mark"><Check /></div>
          <p className="eyebrow">Ingestion complete</p>
          <h1>Everything reached its rightful place.</h1>
          <p>The coordinator reports no unresolved mandatory work.</p>
        </section>
      ) : view.terminal_result ? (
        // A terminal run with an outstanding failure is never called complete.
        <section className="loading-state">
          <p>
            The run finished as <strong>{view.terminal_result}</strong>. Its durable
            record is in Run diagnostics below.
          </p>
        </section>
      ) : failures.length > 0 ? (
        // A run with an outstanding failure must never look busy.
        <section className="loading-state">
          <p>This run is stopped on a failure. The exact failure is shown above.</p>
        </section>
      ) : (
        <div className="loading-state">
          <span className="orb" />
          <p>The coordinator is working through this run.</p>
        </div>
      )}

      <RunDiagnostics
        snapshot={snapshot}
        report={report}
        reportFailure={reportFailure}
        contractFailure={contractError}
        draftState={draftState}
        retryHistory={retryHistory}
      />

      <AnimatePresence>
        {celebrate && <EnvelopeFlight onDone={() => setCelebrate(false)} />}
      </AnimatePresence>
    </AppShell>
  );
}
