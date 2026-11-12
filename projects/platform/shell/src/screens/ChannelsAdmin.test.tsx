import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { CONTROL_TOKEN_KEY } from "../storage";

const channel = {
  name: "twilio_sms",
  enabled: false,
  configured: false,
  can_configure: true,
  mode: "Twilio SMS credential",
  docs: "https://console.twilio.com/",
  fields: [{ key: "TWILIO_AUTH_TOKEN", label: "Auth token", secret: true, configured: true }],
  steps: ["Configure a Twilio number."],
  webhook_url: "http://gateway/webhooks/twilio_sms",
};

describe("channel administration", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/channels");
    sessionStorage.setItem(CONTROL_TOKEN_KEY, "control-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
    window.history.pushState({}, "", "/");
  });

  it("shows redacted setup state and persists deliberate activation", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/v1/channel-admin/catalogue") {
        return new Response(JSON.stringify({ channels: [channel] }), { status: 200 });
      }
      if (path === "/v1/control/presence") {
        return new Response(JSON.stringify({ channels: [{
          name: "twilio_sms", kind: "channel", boundary: "in_process",
          health: "disabled", enabled: false,
        }] }), { status: 200 });
      }
      if (path === "/v1/channel-admin/twilio_sms" && init?.method === "PUT") {
        return new Response(JSON.stringify({ status: "saved" }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "unexpected request" }), { status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    expect(await screen.findByRole("heading", { name: "Twilio SMS" })).toBeInTheDocument();
    expect(screen.getByText("stored")).toBeInTheDocument();
    expect(screen.queryByDisplayValue(/secret|token/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("checkbox", { name: /enable adapter/i }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/v1/channel-admin/twilio_sms",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: true, values: {} }) }),
    ));
  });
});
