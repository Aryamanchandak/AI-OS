import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { TOKEN_KEY } from "../storage";

describe("LLM dashboard", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/llm");
    sessionStorage.setItem(TOKEN_KEY, "ai-os-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
    window.history.pushState({}, "", "/");
  });

  it("shows configured providers and sends a test chat with the chosen provider", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/llm/providers") {
        return new Response(JSON.stringify({
          order: ["gemini_1"], providers: ["gemini_1"], models: { gemini_1: "gemini-2.5-flash" }, chat_profiles: {},
        }), { status: 200 });
      }
      if (path === "/api/llm/status") {
        return new Response(JSON.stringify({
          order: ["gemini_1"], live: { gemini_1: { available: true } },
          today: { gemini_1: { calls: 3, input_tokens: 100, output_tokens: 50, dollars: 0.002 } },
        }), { status: 200 });
      }
      if (path === "/api/llm/capabilities") {
        return new Response(JSON.stringify({
          gemini_1: { model: "gemini-2.5-flash", streaming: true, tools: true, vision: true, structured_output: true, reasoning: false, embeddings: false, max_ctx: 1000000 },
        }), { status: 200 });
      }
      if (path === "/api/llm/chat" && init?.method === "POST") {
        return new Response(JSON.stringify({ text: "hi there", provider: "gemini_1" }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "unexpected request" }), { status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    expect(await screen.findByRole("heading", { name: "gemini_1" })).toBeInTheDocument();
    expect(screen.getByText(/3 calls today/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/llm/chat",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(await screen.findByText(/hi there/)).toBeInTheDocument();
  });
});
