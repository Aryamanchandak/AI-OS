import { BookOpen, ExternalLink } from "lucide-react";
import { useCallback, useState } from "react";

import { AppShell } from "../components/AppShell";
import { TokenGate } from "../components/TokenGate";
import { TOKEN_KEY } from "../storage";

const ENDPOINTS: { method: string; path: string; purpose: string }[] = [
  { method: "POST", path: "/api/llm/chat", purpose: "Send a chat request (optional provider, model, stream)." },
  { method: "POST", path: "/api/llm/chat/batch", purpose: "Send several chat requests concurrently." },
  { method: "POST", path: "/api/llm/embed", purpose: "Embed text with a configured embedding provider." },
  { method: "GET", path: "/api/llm/providers", purpose: "List configured providers, models, and chat profiles." },
  { method: "GET", path: "/api/llm/capabilities", purpose: "Per-provider capability flags (streaming, tools, vision…)." },
  { method: "GET", path: "/api/llm/status", purpose: "Live provider availability and today's usage." },
  { method: "GET", path: "/api/llm/calls", purpose: "Recent call log (?limit=&provider=&status=)." },
  { method: "GET", path: "/api/llm/cost/by_principal", purpose: "Spend rolled up by tenant/session/agent dimension." },
  { method: "GET", path: "/api/llm/budget", purpose: "List budget policies and their current burn." },
  { method: "GET", path: "/api/llm/cache/stats", purpose: "Semantic cache hit rate and entry count." },
  { method: "GET", path: "/api/llm/pricing", purpose: "Per-model pricing the meter bills against." },
  { method: "POST", path: "/v1/transcribe", purpose: "Speech-to-text (audio_b64, mime, prefer)." },
  { method: "POST", path: "/v1/speak", purpose: "Text-to-speech (text, voice_id, prefer)." },
];

const PROVIDERS: { name: string; envVar: string; url: string }[] = [
  { name: "OpenAI", envVar: "OPENAI_API_KEY", url: "https://platform.openai.com/api-keys" },
  { name: "Anthropic", envVar: "ANTHROPIC_API_KEY", url: "https://console.anthropic.com/settings/keys" },
  { name: "Gemini", envVar: "GEMINI_API_KEY (or _1.._10 for multiple keys)", url: "https://aistudio.google.com/app/apikey" },
  { name: "Groq", envVar: "GROQ_API_KEY", url: "https://console.groq.com" },
  { name: "Cerebras", envVar: "CEREBRAS_API_KEY", url: "https://cloud.cerebras.ai" },
  { name: "NVIDIA NIM", envVar: "NVIDIA_API_KEY", url: "https://build.nvidia.com" },
  { name: "OpenRouter", envVar: "OPEN_ROUTER_API_KEY", url: "https://openrouter.ai" },
  { name: "GitHub Models", envVar: "GITHUB_ACCESS_TOKEN", url: "https://github.com/marketplace/models" },
  { name: "Ollama (local)", envVar: "OLLAMA_URL (default http://localhost:11434)", url: "https://ollama.com" },
];

const CURL_EXAMPLE = `curl http://localhost:8000/api/llm/chat \\
  -H "Authorization: Bearer $AI_OS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"messages": [{"role": "user", "content": "hello"}], "provider": "gemini_1"}'`;

export function Help() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");

  const lock = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken("");
  }, []);

  if (!token) return (
    <TokenGate
      onUnlock={setToken}
      storageKey={TOKEN_KEY}
      eyebrow="Reference"
      title="Enter your AI OS key."
      description="Unlocks the same session as the rest of the shell."
    />
  );

  return (
    <AppShell onLock={lock} active="help">
      <section className="channel-hero">
        <div>
          <p className="eyebrow">Reference</p>
          <h1>Help &amp;<br />API reference.</h1>
          <p>Every provider is optional — the ones without a key configured are simply skipped by the router. This page reflects what Gateway actually exposes today, not a fixed snapshot.</p>
        </div>
      </section>

      <div className="workspace-body" style={{ display: "grid", gap: 40 }}>
        <section>
          <p className="eyebrow">Try it</p>
          <h2 style={{ margin: "6px 0 14px" }}>HTTP request</h2>
          <div className="evidence-json" style={{ fontSize: 13 }}><pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{CURL_EXAMPLE}</pre></div>
        </section>

        <section>
          <p className="eyebrow">HTTP API reference</p>
          <h2 style={{ margin: "6px 0 14px" }}>Endpoints</h2>
          <table className="diag-table">
            <thead><tr><th>Method</th><th>Path</th><th>Purpose</th></tr></thead>
            <tbody>
              {ENDPOINTS.map((row) => (
                <tr key={row.path}><td><code>{row.method}</code></td><td><code>{row.path}</code></td><td>{row.purpose}</td></tr>
              ))}
            </tbody>
          </table>
        </section>

        <section>
          <p className="eyebrow">Provider keys</p>
          <h2 style={{ margin: "6px 0 14px" }}>Where to get one</h2>
          <ul className="roadmap-list">
            {PROVIDERS.map((provider) => (
              <li className="roadmap-row" key={provider.name}>
                <code>{provider.envVar}</code>
                <span className="roadmap-summary">{provider.name}</span>
                <a className="roadmap-status" href={provider.url} target="_blank" rel="noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                  Sign up <ExternalLink size={12} />
                </a>
              </li>
            ))}
          </ul>
          <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 14, display: "flex", alignItems: "center", gap: 8 }}>
            <BookOpen size={15} /> Check <a href="/llm" style={{ color: "var(--amber-dark)" }}>the LLM dashboard</a> for which of these are actually configured right now.
          </p>
        </section>
      </div>
    </AppShell>
  );
}
