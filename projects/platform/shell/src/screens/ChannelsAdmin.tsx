import { Activity, Check, CircleOff, ExternalLink, KeyRound, Radio, Save, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "../components/AppShell";
import { Button } from "../components/primitives";
import { TokenGate } from "../components/TokenGate";
import { CONTROL_TOKEN_KEY } from "../storage";

type Field = { key: string; label: string; secret: boolean; configured: boolean };
type Channel = {
  name: string;
  enabled: boolean;
  configured: boolean;
  can_configure: boolean;
  mode: string;
  docs: string | null;
  fields: Field[];
  steps: string[];
  webhook_url: string | null;
};
type Presence = {
  name: string;
  kind: string;
  boundary: "in_process" | "worker";
  health: "healthy" | "degraded" | "disabled";
  enabled: boolean;
  detail?: string;
};

async function api<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error(body.detail || `Gateway returned ${response.status}.`);
  return body as T;
}

function title(name: string): string {
  const acronyms = new Set(["sms", "ui", "imap", "stt", "tts"]);
  return name.split("_").map((part) => (
    acronyms.has(part) ? part.toUpperCase() : part[0]?.toUpperCase() + part.slice(1)
  )).join(" ");
}

export function ChannelsAdmin() {
  const [token, setToken] = useState(() => sessionStorage.getItem(CONTROL_TOKEN_KEY) || "");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [presence, setPresence] = useState<Presence[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { enabled: boolean; values: Record<string, string> }>>({});

  const load = useCallback(async () => {
    if (!token) return;
    setStatus("loading");
    setError("");
    try {
      const [catalogue, presenceBody] = await Promise.all([
        api<{ channels: Channel[] }>("/v1/channel-admin/catalogue", token),
        api<{ channels: Presence[] }>("/v1/control/presence", token),
      ]);
      setChannels(catalogue.channels);
      setPresence(presenceBody.channels);
      setDrafts(Object.fromEntries(catalogue.channels.map((channel) => [
        channel.name, { enabled: channel.enabled, values: {} },
      ])));
      setStatus("ready");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The channel registry could not be loaded.");
      setStatus("error");
    }
  }, [token]);

  useEffect(() => { void load(); }, [load]);

  const health = useMemo(
    () => new Map(presence.map((item) => [item.name, item])),
    [presence],
  );
  const activeCount = presence.filter((item) => item.enabled).length;

  const lock = useCallback(() => {
    sessionStorage.removeItem(CONTROL_TOKEN_KEY);
    setToken("");
  }, []);

  const updateDraft = useCallback((name: string, patch: Partial<{ enabled: boolean; values: Record<string, string> }>) => {
    setDrafts((current) => ({ ...current, [name]: { ...current[name], ...patch } }));
  }, []);

  const save = useCallback(async (channel: Channel) => {
    const draft = drafts[channel.name];
    if (!draft) return;
    setSaving(channel.name);
    setError("");
    try {
      await api(`/v1/channel-admin/${encodeURIComponent(channel.name)}`, token, {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Could not save ${channel.name}.`);
    } finally {
      setSaving(null);
    }
  }, [drafts, load, token]);

  if (!token) return (
    <TokenGate
      onUnlock={setToken}
      storageKey={CONTROL_TOKEN_KEY}
      eyebrow="Channel control"
      title="Enter the installation key."
      description="This separate control key can change credentials and activate listeners. It stays in this browser tab."
    />
  );

  return (
    <AppShell onLock={lock} active="channels">
      <section className="channel-hero">
        <div>
          <p className="eyebrow">Gateway integrations</p>
          <h1>Quiet by default.<br />Ready on purpose.</h1>
          <p>Every adapter is installed and observable. Nothing listens, polls, or speaks until you explicitly enable it.</p>
        </div>
        <div className="channel-tally" aria-label="Channel activation summary">
          <span><strong>{presence.length || 23}</strong> registered</span>
          <span><strong>{activeCount}</strong> enabled</span>
          <span><strong>{presence.filter((item) => item.health === "degraded").length}</strong> degraded</span>
        </div>
      </section>

      {error && (
        <div className="error-banner" role="alert">
          <TriangleAlert size={18} /><span>{error}</span>
          {status === "error" && <Button onClick={() => void load()}>Try again</Button>}
        </div>
      )}

      {status === "loading" || status === "idle" ? (
        <div className="loading-state"><span className="orb" /><p>Reading the Gateway registry…</p></div>
      ) : status === "error" ? null : (
        <div className="channel-grid">
          {channels.map((channel) => {
            const state = health.get(channel.name);
            const draft = drafts[channel.name] ?? { enabled: false, values: {} };
            return (
              <article className="channel-card" key={channel.name} data-health={state?.health ?? "disabled"}>
                <header>
                  <div className="channel-mark">{state?.health === "healthy" ? <Activity /> : state?.health === "degraded" ? <TriangleAlert /> : <CircleOff />}</div>
                  <div>
                    <p className="eyebrow">{state?.boundary === "worker" ? "Isolated worker" : "Gateway process"}</p>
                    <h2>{title(channel.name)}</h2>
                  </div>
                  <span className={`health-pill ${state?.health ?? "disabled"}`}>{state?.health ?? "disabled"}</span>
                </header>

                <p className="channel-mode">{channel.mode}</p>
                {state?.detail && <p className="channel-detail">{state.detail}</p>}
                {channel.webhook_url && <code className="webhook-url">{channel.webhook_url}</code>}

                {channel.fields.length > 0 && (
                  <div className="channel-fields">
                    {channel.fields.map((field) => (
                      <label key={field.key}>
                        <span>{field.label} {field.configured && <em><Check size={11} /> stored</em>}</span>
                        <input
                          type={field.secret ? "password" : "text"}
                          value={draft.values[field.key] ?? ""}
                          placeholder={field.configured ? "Leave blank to keep stored value" : "Not configured"}
                          autoComplete="off"
                          onChange={(event) => updateDraft(channel.name, {
                            values: { ...draft.values, [field.key]: event.target.value },
                          })}
                        />
                      </label>
                    ))}
                  </div>
                )}

                <details>
                  <summary>Setup notes</summary>
                  <ol>{channel.steps.map((step) => <li key={step}>{step}</li>)}</ol>
                  {channel.docs && <a href={channel.docs} target="_blank" rel="noreferrer">Provider documentation <ExternalLink size={13} /></a>}
                </details>

                <footer>
                  <label className="activation-toggle">
                    <input
                      type="checkbox"
                      checked={draft.enabled}
                      onChange={(event) => updateDraft(channel.name, { enabled: event.target.checked })}
                    />
                    <span><Radio size={15} /> Enable adapter</span>
                  </label>
                  <Button tone="primary" disabled={saving === channel.name} onClick={() => void save(channel)}>
                    {saving === channel.name ? <KeyRound size={15} /> : <Save size={15} />}
                    {saving === channel.name ? "Saving…" : "Save"}
                  </Button>
                </footer>
              </article>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
