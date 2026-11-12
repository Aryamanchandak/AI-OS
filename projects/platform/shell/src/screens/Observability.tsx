import { TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "../components/AppShell";
import { Button, Metric } from "../components/primitives";
import { TokenGate } from "../components/TokenGate";
import { TOKEN_KEY } from "../storage";
import "./Observability.css";

const ROOT = "/api/llm";

type Call = { provider: string; status: string; model?: string; cost_usd?: number; input_tokens?: number; output_tokens?: number; latency_ms?: number; timestamp?: number };
type CacheStats = { enabled: boolean; entries?: number; hits?: number; lookups?: number; hit_rate?: number; message?: string };
type BudgetPolicy = { principal: string; dimension: string; pattern: string; limit_usd: number; period: string };
type Budgets = { enabled: boolean; policies: BudgetPolicy[] };
type CostSummary = { period: string; dimensions: string[]; totals_usd: Record<string, number> };
type Trace = { trace_id: string; root_span: string; status: string; duration_ms?: number; started_at?: number };
type TraceList = { traces: Trace[] };
type Refusal = { ts: number; method: string; path: string; detail?: { code?: string; limit_usd?: number; projected_usd?: number } };
type RefusalList = { total: number; kept: number; refusals: Refusal[] };

async function api<T>(path: string, token: string, root = ROOT): Promise<T> {
  const response = await fetch(`${root}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  const body = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error((body as { detail?: string }).detail || `Gateway returned ${response.status}.`);
  return body as T;
}

function since(timestamp?: number): string {
  if (!timestamp) return "—";
  const seconds = Math.max(0, Date.now() / 1000 - timestamp);
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

export function Observability() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const [calls, setCalls] = useState<Call[]>([]);
  const [cache, setCache] = useState<CacheStats | null>(null);
  const [budgets, setBudgets] = useState<Budgets | null>(null);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [traces, setTraces] = useState<Trace[]>([]);
  const [refusals, setRefusals] = useState<RefusalList | null>(null);
  const [loadStatus, setLoadStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    setLoadStatus("loading");
    setError("");
    try {
      const [callRows, cacheStats, budgetList, costRollup, traceList, refusalList] = await Promise.all([
        api<Call[]>("/calls?limit=50", token),
        api<CacheStats>("/cache/stats", token),
        api<Budgets>("/budget", token),
        api<CostSummary>("/cost/by_principal?period=day", token),
        api<TraceList>("/traces/recent", token, "/api/observability"),
        api<RefusalList>("/refusals", token, "/api/observability"),
      ]);
      setCalls(callRows); setCache(cacheStats); setBudgets(budgetList); setCost(costRollup);
      setTraces(traceList.traces); setRefusals(refusalList);
      setLoadStatus("ready");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Observability data could not be loaded.");
      setLoadStatus("error");
    }
  }, [token]);

  useEffect(() => { void load(); }, [load]);

  const lock = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken("");
  }, []);

  if (!token) return (
    <TokenGate
      onUnlock={setToken}
      storageKey={TOKEN_KEY}
      eyebrow="Agent economics"
      title="Enter your AI OS key."
      description="Unlocks the same session as the rest of the shell."
    />
  );

  return (
    <AppShell onLock={lock} active="observability">
      <section className="channel-hero">
        <div>
          <p className="eyebrow">Agent economics</p>
          <h1>Cost, cache,<br />and the call log.</h1>
          <p>Review calls, spend, budgets, and cache activity alongside recent request traces and budget refusals.</p>
        </div>
        <div className="channel-tally" aria-label="Spend today">
          <span><strong>${cost ? Object.values(cost.totals_usd).reduce((a, b) => a + b, 0).toFixed(4) : "0.0000"}</strong> spent today</span>
          <span><strong>{budgets?.policies.length ?? 0}</strong> budget policies</span>
          <Button onClick={() => void load()} disabled={loadStatus === "loading"}>Refresh</Button>
        </div>
      </section>

      {error && (
        <div className="error-banner" role="alert">
          <TriangleAlert size={18} /><span>{error}</span>
          {loadStatus === "error" && <Button onClick={() => void load()}>Try again</Button>}
        </div>
      )}

      {loadStatus === "loading" || loadStatus === "idle" ? (
        <div className="loading-state"><span className="orb" /><p>Reading the ledger…</p></div>
      ) : loadStatus === "error" ? null : (
        <div style={{ display: "grid", gap: 40 }}>
          <section>
            <p className="eyebrow">Request traces</p>
            <h2 className="observability-section-title">Recent traces</h2>
            <p>Recent traces are kept in memory and reset when Gateway restarts.</p>
            {traces.length ? (
              <div className="observability-table-scroll">
                <table className="diag-table">
                  <thead><tr><th scope="col">Trace</th><th scope="col">Request</th><th scope="col">Status</th><th scope="col">Duration</th></tr></thead>
                  <tbody>{traces.map((trace) => (
                    <tr key={trace.trace_id}>
                      <td><code>{trace.trace_id}</code></td><td>{trace.root_span}</td><td>{trace.status}</td>
                      <td>{trace.duration_ms == null ? "—" : `${trace.duration_ms.toFixed(1)}ms`}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <p>No request traces recorded yet.</p>}
          </section>

          <section>
            <p className="eyebrow">Budget admission</p>
            <h2 className="observability-section-title">Budget refusals</h2>
            <p>{refusals?.total ?? 0} refused requests since Gateway started.</p>
            {refusals?.refusals.length ? (
              <div className="observability-table-scroll">
                <table className="diag-table">
                  <thead><tr><th scope="col">When</th><th scope="col">Request</th><th scope="col">Reason</th><th scope="col">Limit</th></tr></thead>
                  <tbody>{refusals.refusals.map((refusal) => (
                    <tr key={`${refusal.ts}:${refusal.method}:${refusal.path}`}>
                      <td>{since(refusal.ts)}</td><td>{refusal.method} {refusal.path}</td>
                      <td>{refusal.detail?.code ?? "Budget refusal"}</td>
                      <td>{refusal.detail?.limit_usd == null ? "—" : `$${refusal.detail.limit_usd.toFixed(2)}`}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <p>No budget refusals recorded yet.</p>}
          </section>

          <section>
            <p className="eyebrow">Semantic cache</p>
            <h2 style={{ margin: "6px 0 14px" }}>Cache</h2>
            {cache?.enabled ? (
              <div className="metrics" style={{ gridTemplateColumns: "repeat(3, minmax(160px, 1fr))" }}>
                <Metric label="Entries" value={cache.entries ?? 0} />
                <Metric label="Hit rate" value={`${((cache.hit_rate ?? 0) * 100).toFixed(1)}%`} />
                <Metric label="Lookups" value={cache.lookups ?? 0} />
              </div>
            ) : (
              <p style={{ color: "var(--muted)" }}>{cache?.message ?? "Semantic cache is not enabled."}</p>
            )}
          </section>

          <section>
            <p className="eyebrow">Spend by dimension</p>
            <h2 style={{ margin: "6px 0 14px" }}>Cost today</h2>
            <div className="metrics" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
              {cost && Object.entries(cost.totals_usd).map(([dimension, total]) => (
                <Metric key={dimension} label={dimension} value={`$${total.toFixed(4)}`} />
              ))}
            </div>
          </section>

          <section>
            <p className="eyebrow">Budgets</p>
            <h2 style={{ margin: "6px 0 14px" }}>Policies</h2>
            {budgets && budgets.policies.length > 0 ? (
              <table className="diag-table">
                <thead><tr><th>Principal</th><th>Dimension</th><th>Limit</th><th>Period</th></tr></thead>
                <tbody>
                  {budgets.policies.map((policy) => (
                    <tr key={policy.principal}>
                      <td>{policy.pattern}</td><td>{policy.dimension}</td>
                      <td>${policy.limit_usd.toFixed(2)}</td><td>{policy.period}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p style={{ color: "var(--muted)" }}>No budget policies loaded. POST /api/llm/budget or add one to budgets.yaml.</p>}
          </section>

          <section>
            <p className="eyebrow">Ledger</p>
            <h2 style={{ margin: "6px 0 14px" }}>Recent calls</h2>
            {calls.length > 0 ? (
              <table className="diag-table">
                <thead><tr><th>When</th><th>Provider</th><th>Model</th><th>Status</th><th>Tokens</th><th>Cost</th><th>Latency</th></tr></thead>
                <tbody>
                  {calls.map((call, index) => (
                    <tr key={index} data-status={call.status !== "ok" ? "failed" : undefined}>
                      <td>{since(call.timestamp)}</td><td>{call.provider}</td><td>{call.model ?? "—"}</td>
                      <td>{call.status}</td>
                      <td>{(call.input_tokens ?? 0) + (call.output_tokens ?? 0)}</td>
                      <td>${(call.cost_usd ?? 0).toFixed(5)}</td>
                      <td>{call.latency_ms ? `${call.latency_ms}ms` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p style={{ color: "var(--muted)" }}>No calls in the ledger yet. Send a request from the <a href="/llm" style={{ color: "var(--amber-dark)" }}>LLM dashboard</a> and it appears here.</p>}
          </section>
        </div>
      )}
    </AppShell>
  );
}
