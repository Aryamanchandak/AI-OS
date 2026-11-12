import { Activity } from "lucide-react";

import type { RunReport, Snapshot } from "../api/client";
import type { Failure } from "../failures";

const NONE = "none";

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="diag-fact">
      <dt>{label}</dt>
      <dd>{value === null || value === undefined || value === "" ? NONE : value}</dd>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="diag-group">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function CountList({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  // An empty group is stated as zero, never omitted: a missing row and a row
  // reading zero mean different things to someone diagnosing a run.
  if (entries.length === 0) return <p className="diag-empty">none</p>;
  return (
    <dl className="diag-facts">
      {entries.map(([key, value]) => (
        <Fact key={key} label={key} value={String(value)} />
      ))}
    </dl>
  );
}

/**
 * Run diagnostics — an expandable panel inside the one ordered ingestion
 * screen, not a second application or a second queue.
 *
 * It renders backend facts only. It computes no percentages, invents no
 * events, and keeps no frontend audit store.
 */
export function RunDiagnostics({
  snapshot,
  report,
  reportFailure,
  contractFailure,
  draftState,
  retryHistory,
}: {
  snapshot: Snapshot | null;
  report: RunReport | null;
  reportFailure: Failure | null;
  /** A legal action the current adapter cannot serialize. */
  contractFailure: Failure | null;
  /** "Draft retained" / "Draft cleared after confirmed success" for the item. */
  draftState: string | null;
  retryHistory: string[];
}) {
  const view = snapshot?.view ?? null;
  const operation = snapshot?.operation ?? null;

  return (
    <details className="diagnostics">
      <summary>
        <Activity size={16} aria-hidden="true" /> Run diagnostics
      </summary>
      <div className="diag-body">
        <Group title="Run">
          <dl className="diag-facts">
            <Fact label="Run id" value={view?.run_id} />
            <Fact label="Reviewer" value={snapshot?.reviewer} />
            <Fact label="Operation" value={operation?.name} />
            <Fact label="Operation state" value={operation?.state} />
            <Fact label="Revision" value={operation ? String(operation.revision) : null} />
            <Fact label="Stage" value={view?.stage} />
            <Fact label="Stage status" value={view?.stage_status} />
            <Fact label="Terminal result" value={view?.terminal_result} />
          </dl>
        </Group>

        <Group title="Stages">
          {view && view.stages.length > 0 ? (
            <table className="diag-table">
              <thead>
                <tr><th>Stage</th><th>Status</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {view.stages.map((stage) => (
                  <tr key={stage.stage} data-status={stage.status}>
                    <td>{stage.stage}</td>
                    <td>{stage.status}</td>
                    <td>
                      {Object.keys(stage.detail ?? {}).length === 0
                        ? NONE
                        : JSON.stringify(stage.detail)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="diag-empty">No stages returned yet.</p>
          )}
        </Group>

        <Group title="Progress">
          <dl className="diag-facts">
            <Fact label="Intake total" value={String(view?.progress.intake_total ?? 0)} />
            <Fact label="Intake resolved" value={String(view?.progress.intake_resolved ?? 0)} />
            <Fact label="Envelopes flagged" value={String(view?.progress.envelopes_flagged ?? 0)} />
            <Fact label="Envelopes resolved" value={String(view?.progress.envelopes_resolved ?? 0)} />
          </dl>
        </Group>

        <Group title="Pending decision">
          {view?.pending ? (
            <dl className="diag-facts">
              <Fact label="Gate" value={view.pending.gate} />
              <Fact label="Adapter" value={view.pending.adapter} />
              <Fact label="Item id" value={view.pending.item_id} />
              <Fact label="Allowed actions" value={view.pending.allowed_actions.join(", ")} />
              <Fact label="Blocking reason" value={view.pending.blocking_reason} />
            </dl>
          ) : (
            <p className="diag-empty">Nothing is awaiting a decision.</p>
          )}
        </Group>

        <Group title="Last error">
          {view?.last_error ? (
            <dl className="diag-facts">
              <Fact label="Stage" value={view.last_error.stage} />
              <Fact label="Message" value={view.last_error.message} />
              <Fact label="Retryable" value={view.last_error.retryable ? "yes" : "no"} />
            </dl>
          ) : operation?.state === "failed" ? (
            <dl className="diag-facts">
              <Fact label="Failed operation" value={operation.name} />
              <Fact label="Message" value={operation.error} />
            </dl>
          ) : (
            <p className="diag-empty">No error reported.</p>
          )}
        </Group>

        <Group title="Action contract">
          {contractFailure ? (
            <dl className="diag-facts">
              {contractFailure.facts.map((fact) => (
                <Fact key={fact.label} label={fact.label} value={fact.value} />
              ))}
              <Fact label="Message" value={contractFailure.message} />
            </dl>
          ) : (
            <p className="diag-empty">
              Every action the coordinator returned is supported.
            </p>
          )}
        </Group>

        <Group title="Local draft">
          <p className="diag-empty">{draftState ?? "No local draft for this item."}</p>
        </Group>

        <Group title="Retries">
          {retryHistory.length === 0 ? (
            <p className="diag-empty">No retry has been requested.</p>
          ) : (
            <ul className="diag-list">
              {retryHistory.map((entry) => <li key={entry}>{entry}</li>)}
            </ul>
          )}
        </Group>

        {reportFailure && (
          <Group title="Terminal report">
            <p className="diag-empty">
              {reportFailure.heading}: {reportFailure.message}
            </p>
          </Group>
        )}

        {report && <TerminalReport report={report} />}
      </div>
    </details>
  );
}

/** The durable facts a finished run left behind, from GET /run/{id}/report. */
function TerminalReport({ report }: { report: RunReport }) {
  const intake = report.intake;
  return (
    <>
      <Group title="Terminal report">
        <dl className="diag-facts">
          <Fact label="Run id" value={report.run_id} />
          <Fact label="Terminal result" value={report.terminal_result} />
          <Fact label="Failed from" value={report.failed_from} />
          <Fact
            label="Last error"
            value={report.last_error
              ? `${report.last_error.stage}: ${report.last_error.message} `
                + `(${report.last_error.retryable ? "retryable" : "not retryable"})`
              : null}
          />
        </dl>
      </Group>

      <Group title="Stage ledger">
        {(report.stages ?? []).length === 0 ? (
          <p className="diag-empty">No stages recorded.</p>
        ) : (
          <table className="diag-table">
            <thead><tr><th>Stage</th><th>Status</th><th>Detail</th></tr></thead>
            <tbody>
              {(report.stages ?? []).map((stage, index) => (
                <tr key={`${stage.stage}-${index}`} data-status={stage.status}>
                  <td>{stage.stage}</td>
                  <td>{stage.status}</td>
                  <td>
                    {Object.keys(stage.detail ?? {}).length === 0
                      ? NONE
                      : JSON.stringify(stage.detail)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Group>

      <Group title="Intake outcomes">
        <dl className="diag-facts">
          <Fact label="Discovered" value={String(intake?.discovered ?? 0)} />
          <Fact label="Published" value={String(intake?.published ?? 0)} />
          <Fact label="Discarded" value={String(intake?.discarded ?? 0)} />
          <Fact label="Retake" value={String(intake?.retake ?? 0)} />
          <Fact label="Duplicate" value={String(intake?.duplicate ?? 0)} />
          <Fact label="Failed" value={String(intake?.failed ?? 0)} />
          <Fact label="Gate events" value={String((intake?.gates ?? []).length)} />
        </dl>
      </Group>

      <Group title="Vault notes written">
        {(report.vault_notes_written ?? []).length === 0 ? (
          <p className="diag-empty">none</p>
        ) : (
          <ul className="diag-list">
            {(report.vault_notes_written ?? []).map((note) => <li key={note}>{note}</li>)}
          </ul>
        )}
      </Group>

      <Group title="Capture counts">
        <dl className="diag-facts">
          <Fact label="Total" value={String(report.capture_counts?.total ?? 0)} />
          <Fact label="New" value={String(report.capture_counts?.new ?? 0)} />
          <Fact label="Duplicate" value={String(report.capture_counts?.duplicate ?? 0)} />
        </dl>
      </Group>

      <Group title="Processing counts">
        <CountList counts={report.processing_counts ?? {}} />
      </Group>

      <Group title="Proposal review counts">
        <dl className="diag-facts">
          <Fact label="Approve" value={String(report.review?.approve ?? 0)} />
          <Fact label="Edit" value={String(report.review?.edit ?? 0)} />
          <Fact label="Reject" value={String(report.review?.reject ?? 0)} />
          <Fact label="Still blocked" value={String(report.review?.still_blocked ?? 0)} />
        </dl>
      </Group>

      <Group title="Dispatch counts">
        <CountList counts={report.dispatch_counts ?? {}} />
      </Group>

      <Group title="Retryable failures">
        {(report.retryable_failures ?? []).length === 0 ? (
          <p className="diag-empty">none</p>
        ) : (
          <ul className="diag-list">
            {(report.retryable_failures ?? []).map((failure, index) => (
              <li key={index}>{JSON.stringify(failure)}</li>
            ))}
          </ul>
        )}
      </Group>

      <Group title="Discrepancies">
        {(report.discrepancies ?? []).length === 0 ? (
          <p className="diag-empty">none</p>
        ) : (
          <ul className="diag-list">
            {(report.discrepancies ?? []).map((entry) => <li key={entry}>{entry}</li>)}
          </ul>
        )}
      </Group>

      <Group title="Final progress">
        <dl className="diag-facts">
          <Fact label="Intake total" value={String(report.progress?.intake_total ?? 0)} />
          <Fact label="Intake resolved" value={String(report.progress?.intake_resolved ?? 0)} />
          <Fact label="Envelopes flagged" value={String(report.progress?.envelopes_flagged ?? 0)} />
          <Fact label="Envelopes resolved" value={String(report.progress?.envelopes_resolved ?? 0)} />
        </dl>
      </Group>

      <details className="diag-raw">
        <summary>Raw report JSON</summary>
        <pre>{JSON.stringify(report, null, 2)}</pre>
      </details>
    </>
  );
}
