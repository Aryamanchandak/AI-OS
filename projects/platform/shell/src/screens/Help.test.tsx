import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import App from "../App";
import { TOKEN_KEY } from "../storage";

describe("help", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/help");
    sessionStorage.setItem(TOKEN_KEY, "ai-os-token");
  });

  afterEach(() => {
    sessionStorage.clear();
    window.history.pushState({}, "", "/");
  });

  it("lists the current HTTP API endpoints and provider signup links", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /help/i })).toBeInTheDocument();
    expect(screen.getByText("/api/llm/chat")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /sign up/i }).length).toBeGreaterThan(0);
  });
});
