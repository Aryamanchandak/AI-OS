import { Cpu, Send, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "../components/AppShell";
import { Button } from "../components/primitives";
import { TokenGate } from "../components/TokenGate";
import { TOKEN_KEY } from "../storage";

const ROOT = "/api/llm";

type Providers = {
  order: string[];
  providers: string[];
  models: Record<string, string>;
  chat_profiles: Record<string, { provider: string; available: boolean }>;
};
type Status = { order: string[]; live: Record<string, { available: boolean }>; today: Record<string, { calls: number; input_tokens: number; output_tokens: number; dollars: number }> };
type Capabilities = Record<string, { model: string; streaming: boolean; tools: boolean; vision: boolean; structured_output: boolean; reasoning: boolean; embeddings: boolean; max_ctx: number }>;

async function api<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${ROOT}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error((body as { detail?: string }).detail || `Gateway returned ${response.status}.`);
  return body as T;
}

function pill(active: boolean, label: string) {
  return <span key={label} className={`health-pill ${active ? "healthy" : ""}`}>{label}</span>;
}

export function LLMDashboard() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const [providers, setProviders] = useState<Providers | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [loadStatus, setLoadStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState("");

  const [prompt, setPrompt] = useState("Say hello in five words.");
  const [testProvider, setTestProvider] = useState("");
  const [testOut, setTestOut] = useState("");
  const [testing, setTesting] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoadStatus("loading");
    setError("");
    try {
      const [p, s, c] = await Promise.all([
        api<Providers>("/providers", token),
        api<Status>("/status", token),
        api<Capabilities>("/capabilities", token),
      ]);
      setProviders(p); setStatus(s); setCapabilities(c);
      setLoadStatus("ready");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The LLM registry could not be loaded.");
      setLoadStatus("error");
    }
  }, [token]);

  useEffect(() => { void load(); }, [load]);

  const lock = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken("");
  }, []);

  const runTest = useCallback(async () => {
    setTesting(true);
    setTestOut("");
    try {
      const body: { messages: { role: string; content: string }[]; provider?: string } = {
        messages: [{ role: "user", content: prompt }],
      };
      if (testProvider) body.provider = testProvider;
      const response = await api<{ text?: string; provider?: string; error?: string }>("/chat", token, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setTestOut(response.text ? `[${response.provider}] ${response.text}` : JSON.stringify(response, null, 2));
    } catch (cause) {
      setTestOut(cause instanceof Error ? cause.message : "Request failed.");
    } finally {
      setTesting(false);
    }
  }, [prompt, testProvider, token]);

  if (!token) return (
    <TokenGate
      onUnlock={setToken}
      storageKey={TOKEN_KEY}
      eyebrow="LLM orchestration"
      title="Enter your AI OS key."
      description="Unlocks the same session as the rest of the shell."
    />
  );

  const order = providers?.order ?? [];

  return (
    <AppShell onLock={lock} active="llm">
      <section className="channel-hero">
        <div>
          <p className="eyebrow">LLM orchestration</p>
          <h1>Every provider,<br />one contract.</h1>
          <p>Chat, vision, and embedding calls route through a shared candidate order with failover, budgets, and a semantic cache — see <a href="/observability" style={{ color: "var(--amber-dark)" }}>Observability</a> for cost and traces.</p>
        </div>
        <div className="channel-tally" aria-label="Provider summary">
          <span><strong>{order.length}</strong> configured</span>
          <span><strong>{Object.values(status?.today ?? {}).reduce((n, row) => n + (row.calls ?? 0), 0)}</strong> calls today</span>
        </div>
      </section>

      {error && (
        <div className="error-banner" role="alert">
          <TriangleAlert size={18} /><span>{error}</span>
          {loadStatus === "error" && <Button onClick={() => void load()}>Try again</Button>}
        </div>
      )}

      {loadStatus === "loading" || loadStatus === "idle" ? (
        <div className="loading-state"><span className="orb" /><p>Reading the provider registry…</p></div>
      ) : loadStatus === "error" ? null : (
        <>
          <div className="channel-grid">
            {order.map((name) => {
              const caps = capabilities?.[name];
              const usage = status?.today?.[name];
              const live = status?.live?.[name]?.available ?? true;
              return (
                <article className="channel-card" key={name} data-health={live ? "healthy" : "degraded"}>
                  <header>
                    <div className="channel-mark"><Cpu size={19} /></div>
                    <div>
                      <p className="eyebrow">{caps?.model ?? providers?.models[name] ?? "unknown model"}</p>
                      <h2>{name}</h2>
                    </div>
                    <span className={`health-pill ${live ? "healthy" : ""}`}>{live ? "available" : "degraded"}</span>
                  </header>
                  {caps && (
                    <div className="caps-row" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {pill(caps.streaming, "streaming")}
                      {pill(caps.tools, "tools")}
                      {pill(caps.vision, "vision")}
                      {pill(caps.structured_output, "structured out")}
                      {pill(caps.reasoning, "reasoning")}
                      {pill(caps.embeddings, "embeddings")}
                    </div>
                  )}
                  <p className="channel-mode">max context: {caps?.max_ctx?.toLocaleString() ?? "—"} tokens</p>
                  {usage && (
                    <p className="channel-detail">
                      {usage.calls} call{usage.calls === 1 ? "" : "s"} today · {usage.input_tokens + usage.output_tokens} tokens · ${usage.dollars.toFixed(4)}
                    </p>
                  )}
                </article>
              );
            })}
          </div>

          <section style={{ marginTop: 40 }}>
            <p className="eyebrow">Try it</p>
            <h2 style={{ margin: "6px 0 14px" }}>Send a test chat</h2>
            <div className="test-area" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                rows={3}
                style={{ flex: 1, minWidth: 280 }}
              />
              <select value={testProvider} onChange={(event) => setTestProvider(event.target.value)} style={{ padding: "12px 14px", borderRadius: 12, border: "1px solid var(--line)" }}>
                <option value="">auto (failover order)</option>
                {order.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
              <Button tone="primary" disabled={testing || !prompt.trim()} onClick={() => void runTest()}>
                <Send size={15} /> {testing ? "Sending…" : "Send"}
              </Button>
            </div>
            {testOut && <div className="evidence-json" style={{ marginTop: 14, maxHeight: 240 }}><pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{testOut}</pre></div>}
          </section>
        </>
      )}
    </AppShell>
  );
}
