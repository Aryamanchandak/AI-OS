import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { TOKEN_KEY } from "../storage";

describe("observability", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/observability");
    sessionStorage.setItem(TOKEN_KEY, "ai-os-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
    window.history.pushState({}, "", "/");
  });

  it("renders cache stats, budgets, and the recent call ledger", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/llm/calls?limit=50") {
        return new Response(JSON.stringify([
          { provider: "gemini_1", status: "ok", model: "gemini-2.5-flash", cost_usd: 0.001, input_tokens: 10, output_tokens: 5, latency_ms: 320, timestamp: Date.now() / 1000 },
        ]), { status: 200 });
      }
      if (path === "/api/llm/cache/stats") {
        return new Response(JSON.stringify({ enabled: true, entries: 12, hits: 4, lookups: 10, hit_rate: 0.4 }), { status: 200 });
      }
      if (path === "/api/llm/budget") {
        return new Response(JSON.stringify({ enabled: true, policies: [{ principal: "tenant:default", dimension: "tenant", pattern: "default", limit_usd: 5, period: "day" }] }), { status: 200 });
      }
      if (path === "/api/llm/cost/by_principal?period=day") {
        return new Response(JSON.stringify({ period: "day", dimensions: ["tenant"], totals_usd: { tenant: 0.001 } }), { status: 200 });
      }
      if (path === "/api/observability/traces/recent") {
        return new Response(JSON.stringify({ traces: [{ trace_id: "trace-1", root_span: "POST /api/llm/chat", status: "ERROR", duration_ms: 2 }] }), { status: 200 });
      }
      if (path === "/api/observability/refusals") {
        return new Response(JSON.stringify({ total: 1, kept: 1, refusals: [{ ts: Date.now() / 1000, method: "POST", path: "/v1/chat", detail: { code: "budget_exceeded", limit_usd: 0 } }] }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "unexpected request" }), { status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    expect(await screen.findByText("gemini_1")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("default")).toBeInTheDocument();
    expect(screen.getByText("trace-1")).toBeInTheDocument();
    expect(screen.getByText("budget_exceeded")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/observability/traces/recent", { headers: { Authorization: "Bearer ai-os-token" } });
  });

  it("shows a retryable error when observability cannot load", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Diagnostics unavailable" }), { status: 503 })));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Diagnostics unavailable");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
