import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type RunReport, type Snapshot } from "../api/client";
import {
  coordinatorFailure,
  operationFailure,
  transportFailure,
  type Failure,
} from "../failures";

const POLL_MS = 750;
const TERMINAL = new Set(["complete", "failed"]);

/**
 * How the run was brought into existence. The distinction matters because a
 * failed start has no coordinator run to retry, while a failed stage does.
 */
export type StartState =
  | "not-attempted"
  | "starting"
  | "started"
  /** Start itself failed before any RunView existed. */
  | "failed";

export function useIngestion(token: string) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [transport, setTransport] = useState<Failure | null>(null);
  const [loading, setLoading] = useState(true);
  const [startState, setStartState] = useState<StartState>("not-attempted");
  const [report, setReport] = useState<RunReport | null>(null);
  const [reportFailure, setReportFailure] = useState<Failure | null>(null);

  // Only the first start is automatic. Every later attempt is the user's
  // explicit action, so a coordinator that fails on start cannot be retried in
  // a loop by the poller.
  const autoStarted = useRef(false);
  const requestedReport = useRef<string | null>(null);
  // A 401 means this token is wrong, not that the request happened to fail —
  // retrying it on the poll interval would just repeat the same 401 forever.
  // Only a new token (a fresh mount of this hook) clears it.
  const unauthorizedRef = useRef(false);
  const [unauthorized, setUnauthorized] = useState(false);

  const poll = useCallback(async (): Promise<Snapshot | null> => {
    try {
      const next = await api.snapshot(token);
      setSnapshot(next);
      setTransport(null);
      return next;
    } catch (cause) {
      const failure = transportFailure(cause);
      setTransport(failure);
      if (failure.status === 401) {
        unauthorizedRef.current = true;
        setUnauthorized(true);
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, [token]);

  const start = useCallback(async () => {
    setStartState("starting");
    try {
      const accepted = await api.start(token);
      setSnapshot(accepted);
      setTransport(null);
      setStartState("started");
    } catch (cause) {
      // A rejected start never reached the coordinator. The 202 path is
      // handled by the poller below, which sees operation.state === "failed".
      setTransport(transportFailure(cause));
      setStartState("failed");
    }
  }, [token]);

  const refresh = useCallback(async () => {
    await poll();
  }, [poll]);

  /** Explicit user recovery for a start that never produced a run. */
  const startAgain = useCallback(async () => {
    autoStarted.current = true;
    setReport(null);
    setReportFailure(null);
    requestedReport.current = null;
    await start();
  }, [start]);

  /**
   * Explicit user recovery for a coordinator stage the backend marked
   * retryable. Resolves true when the gateway accepted the request, so the
   * caller only starts waiting for a confirmation that can actually arrive.
   */
  const retry = useCallback(async (): Promise<boolean> => {
    try {
      const accepted = await api.retry(token);
      setSnapshot(accepted);
      setTransport(null);
      return true;
    } catch (cause) {
      setTransport(transportFailure(cause));
      return false;
    }
  }, [token]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    unauthorizedRef.current = false;
    setUnauthorized(false);

    const tick = async () => {
      // A prior tick already found this token unauthorized; every 401 since
      // has been identical, so stop spending requests on it. Re-entering a
      // token remounts this effect (token is a dependency) and clears the ref.
      if (unauthorizedRef.current) return;
      const next = await poll();
      if (cancelled || !next) return;
      if (!next.view && next.operation.state === "idle" && !autoStarted.current) {
        autoStarted.current = true;
        await start();
      }
    };

    void tick();
    const id = window.setInterval(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [poll, start, token]);

  // The durable terminal record, fetched once per terminal run.
  const terminalRunId = snapshot?.view?.terminal_result
    && TERMINAL.has(snapshot.view.terminal_result)
    ? snapshot.view.run_id
    : null;

  useEffect(() => {
    if (!token || !terminalRunId) return;
    if (requestedReport.current === terminalRunId) return;
    requestedReport.current = terminalRunId;
    void api.report(token, terminalRunId)
      .then((fetched) => {
        setReport(fetched);
        setReportFailure(null);
      })
      .catch((cause: unknown) => {
        setReport(null);
        setReportFailure(transportFailure(cause));
      });
  }, [terminalRunId, token]);

  const operation = useMemo(() => operationFailure(snapshot), [snapshot]);
  const coordinator = useMemo(() => coordinatorFailure(snapshot), [snapshot]);

  // A start that the gateway accepted with 202 and that then failed inside the
  // service leaves no view behind. Without this the screen shows "Starting the
  // ingestion run…" forever, because the guard blocks another attempt.
  const startFailed =
    startState === "failed"
    || (!snapshot?.view
      && snapshot?.operation.state === "failed"
      && snapshot.operation.name === "start");

  return {
    snapshot,
    loading,
    transportFailure: transport,
    operationFailure: operation,
    coordinatorFailure: coordinator,
    reportFailure,
    report,
    startFailed,
    startState,
    unauthorized,
    refresh,
    reconnect: refresh,
    startAgain,
    retry,
  };
}
