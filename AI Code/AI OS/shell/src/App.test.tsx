import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { draftKey } from "./drafts";
import { TOKEN_KEY } from "./storage";
import { bookPending, cleanupPending, cleanupUnavailablePending, runReport, snapshot, view } from "./test/factories";
import { fakeGateway } from "./test/server";

beforeEach(() => {
  sessionStorage.setItem(TOKEN_KEY, "test-token");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const failureSurface = () => screen.getByRole("region", { name: "Failure details" });
const announcer = () => screen.getByTestId("failure-announcer");

describe("background service operation failure", () => {
  it("shows the named operation, the exact error and the revision", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({ pending: null }),
        operation: {
          state: "failed",
          name: "decision",
          error: "Neo4j refused the write",
          revision: 3,
        },
      })],
    });

    render(<App />);

    const surface = await screen.findByRole("region", { name: "Failure details" });
    expect(within(surface).getByText("decision failed")).toBeInTheDocument();
    // The exact backend message survives; it is never replaced.
    expect(within(surface).getByText("Neo4j refused the write")).toBeInTheDocument();
    expect(within(surface).getByText("Revision")).toBeInTheDocument();
  });
});

describe("coordinator stage failure", () => {
  it("shows the stage, message and retryability, and offers Retry", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: null,
          stage_status: "failed",
          last_error: {
            stage: "capture_obsidian",
            message: "the vault is read-only",
            retryable: true,
          },
        }),
      })],
    });

    render(<App />);

    const surface = await screen.findByRole("region", { name: "Failure details" });
    expect(within(surface).getByText("capture_obsidian failed")).toBeInTheDocument();
    expect(within(surface).getByText("the vault is read-only")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();

    // A stopped run must not keep presenting itself as working.
    expect(document.querySelector(".orb")).toBeNull();
    expect(screen.getByText(/This run is stopped on a failure/)).toBeInTheDocument();
  });

  it("does not offer Retry for a failure the coordinator marked non-retryable", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: null,
          last_error: {
            stage: "preflight",
            message: "the drop folder is missing",
            retryable: false,
          },
        }),
      })],
    });

    render(<App />);

    await screen.findByText("preflight failed");
    expect(screen.queryByRole("button", { name: /^Retry/ })).not.toBeInTheDocument();
  });

  it("renders both layers separately when the service and coordinator both failed", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: null,
          last_error: { stage: "dispatch_retry", message: "target unreachable", retryable: true },
        }),
        operation: { state: "failed", name: "retry", error: "worker thread died", revision: 5 },
      })],
    });

    render(<App />);

    const surface = await screen.findByRole("region", { name: "Failure details" });
    // Neither message is merged into or replaced by the other.
    expect(within(surface).getByText("retry failed")).toBeInTheDocument();
    expect(within(surface).getByText("worker thread died")).toBeInTheDocument();
    expect(within(surface).getByText("dispatch_retry failed")).toBeInTheDocument();
    expect(within(surface).getByText("target unreachable")).toBeInTheDocument();
  });
});

describe("failure announcements", () => {
  it("announces a new failure once and does not move focus", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: null,
          last_error: { stage: "capture_obsidian", message: "the vault is read-only", retryable: true },
        }),
      })],
    });

    render(<App />);
    await screen.findByText("capture_obsidian failed");

    const live = announcer();
    expect(live).toHaveAttribute("role", "alert");
    expect(live).toHaveTextContent("capture_obsidian failed. the vault is read-only");

    // Focus stays where the user left it; nothing is focused programmatically.
    expect(document.activeElement).toBe(document.body);
    // The surface is reachable deliberately instead.
    expect(failureSurface()).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("link", { name: "Go to failure details" }))
      .toHaveAttribute("href", "#failure-surface");

    // A live region re-announces when its content is rewritten. Several more
    // polls of the same failure must not touch it at all.
    const mutations: MutationRecord[] = [];
    const observer = new MutationObserver((records) => mutations.push(...records));
    observer.observe(live, { childList: true, characterData: true, subtree: true });

    await new Promise((resolve) => setTimeout(resolve, 1700));
    observer.disconnect();

    expect(mutations).toEqual([]);
    expect(announcer()).toBe(live);
    expect(document.activeElement).toBe(document.body);
  });

  it("announces a new failure whose text reads the same as the previous one", async () => {
    const repeated = {
      stage: "capture_obsidian",
      message: "the vault is read-only",
      retryable: true,
    };
    const gateway = fakeGateway({
      snapshots: [snapshot({
        view: view({ pending: null, last_error: repeated }),
        operation: { state: "idle", revision: 4 },
      })],
    });

    render(<App />);
    await screen.findByText("capture_obsidian failed");
    const first = announcer();

    // The retry ran and the same stage failed again: a different failure, with
    // identical text. Deduplicating on text alone would silence it.
    gateway.setSnapshots([snapshot({
      view: view({ pending: null, last_error: repeated }),
      operation: { state: "idle", revision: 5 },
    })]);

    await waitFor(() => expect(announcer()).not.toBe(first));
    expect(announcer()).toHaveTextContent("capture_obsidian failed. the vault is read-only");
  });
});

describe("a failed start", () => {
  it("stops the spinner, shows the error and offers an explicit Try start again", async () => {
    const gateway = fakeGateway({
      snapshots: [snapshot({
        view: null,
        operation: { state: "failed", name: "start", error: "the drop folder is missing", revision: 0 },
      })],
    });

    render(<App />);

    await screen.findByText("start failed");
    // Also echoed in Run diagnostics, so the assertion is scoped to the surface.
    expect(within(failureSurface()).getByText("the drop folder is missing"))
      .toBeInTheDocument();
    expect(screen.queryByText("Starting the ingestion run…")).not.toBeInTheDocument();

    // No automatic loop: several poll intervals produce no further start call.
    await new Promise((resolve) => setTimeout(resolve, 1700));
    const automaticStarts = gateway.calls.filter(
      (call) => call.path.endsWith("/run/start"),
    ).length;
    expect(automaticStarts).toBeLessThanOrEqual(1);

    await userEvent.click(screen.getByRole("button", { name: /Try start again/ }));
    expect(gateway.called("/run/start")).toBe(true);
  });

  it("recovers when the explicit start attempt succeeds", async () => {
    const gateway = fakeGateway({
      snapshots: [snapshot({
        view: null,
        operation: { state: "failed", name: "start", error: "transient failure", revision: 0 },
      })],
    });

    render(<App />);
    await screen.findByText("start failed");

    gateway.setSnapshots([snapshot({ view: view({ pending: bookPending() }) })]);
    await userEvent.click(screen.getByRole("button", { name: /Try start again/ }));

    expect(await screen.findByText("Confirm the book")).toBeInTheDocument();
  });
});

describe("retry and reconnect", () => {
  it("calls the retry endpoint and records the confirmed retry in diagnostics", async () => {
    const gateway = fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: null,
          last_error: { stage: "capture_obsidian", message: "vault locked", retryable: true },
        }),
        operation: { state: "idle", revision: 4 },
      })],
    });

    render(<App />);
    await screen.findByText("capture_obsidian failed");

    gateway.setSnapshots([snapshot({
      view: view({ pending: null, terminal_result: "complete" }),
      operation: { state: "idle", revision: 5 },
    })]);
    await userEvent.click(screen.getByRole("button", { name: /Retry/ }));

    expect(gateway.called("/run/retry")).toBe(true);
    await waitFor(() =>
      expect(screen.getByText(/Retry confirmed succeeded at revision 5/)).toBeInTheDocument(),
    );
  });

  it("keeps a failed retry prominent with its new message and never auto-retries", async () => {
    const gateway = fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: null,
          last_error: { stage: "capture_obsidian", message: "vault locked", retryable: true },
        }),
      })],
    });

    render(<App />);
    await screen.findByText("capture_obsidian failed");
    await userEvent.click(screen.getByRole("button", { name: /Retry/ }));

    gateway.setSnapshots([snapshot({
      view: view({ pending: null, last_error: null }),
      operation: { state: "failed", name: "retry", error: "the vault is still locked", revision: 4 },
    })]);

    await screen.findByText("retry failed");
    expect(within(failureSurface()).getByText("the vault is still locked"))
      .toBeInTheDocument();

    const before = gateway.calls.filter((call) => call.path.endsWith("/run/retry")).length;
    await new Promise((resolve) => setTimeout(resolve, 1700));
    const after = gateway.calls.filter((call) => call.path.endsWith("/run/retry")).length;
    expect(after).toBe(before);
  });

  it("Reconnect only re-polls; it never retries a stage or resubmits a decision", async () => {
    const gateway = fakeGateway({
      snapshots: [snapshot({ view: view({ pending: bookPending() }) })],
      // Every poll fails at the transport layer.
    });
    gateway.fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      gateway.calls.push({ path: String(input), method: "GET" });
      throw new TypeError("Failed to fetch");
    });

    render(<App />);
    const reconnect = await screen.findByRole("button", { name: /Reconnect/ });
    await userEvent.click(reconnect);

    expect(gateway.called("/run/retry")).toBe(false);
    expect(gateway.called("/run/decision")).toBe(false);
  });
});

describe("transport failures", () => {
  it("names the request and the status and shows the exact server detail", async () => {
    const gateway = fakeGateway({ snapshots: [snapshot()] });
    gateway.fetchMock.mockImplementation(async () =>
      new Response(JSON.stringify({ detail: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<App />);

    const surface = await screen.findByRole("region", { name: "Failure details" });
    expect(within(surface).getByText("Poll run could not be completed")).toBeInTheDocument();
    expect(within(surface).getByText("Unauthorized")).toBeInTheDocument();
    expect(within(surface).getByText("401")).toBeInTheDocument();
  });

  it("offers Re-enter key instead of Reconnect on a 401, and never Reconnect", async () => {
    const gateway = fakeGateway({ snapshots: [snapshot()] });
    gateway.fetchMock.mockImplementation(async () =>
      new Response(JSON.stringify({ detail: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<App />);

    await screen.findByRole("button", { name: /Re-enter key/ });
    // Reconnecting would just resubmit the same wrong token and 401 again —
    // it must never be offered alongside or instead of Re-enter key here.
    expect(screen.queryByRole("button", { name: /^Reconnect/ })).not.toBeInTheDocument();
  });

  it("clicking Re-enter key clears the stored token and returns to the token screen", async () => {
    const gateway = fakeGateway({ snapshots: [snapshot()] });
    gateway.fetchMock.mockImplementation(async () =>
      new Response(JSON.stringify({ detail: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Re-enter key/ }));

    expect(await screen.findByRole("heading", { name: /Enter your AI OS key/ }))
      .toBeInTheDocument();
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("stops polling after the first 401 instead of repeating it every interval", async () => {
    const gateway = fakeGateway({ snapshots: [snapshot()] });
    gateway.fetchMock.mockImplementation(async () =>
      new Response(JSON.stringify({ detail: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<App />);
    await screen.findByRole("button", { name: /Re-enter key/ });
    const before = gateway.calls.length;

    await new Promise((resolve) => setTimeout(resolve, 1700));

    expect(gateway.calls.length).toBe(before);
  });
});

describe("run diagnostics", () => {
  it("shows the active stage ledger with done, skipped and failed rows", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: null,
          stages: [
            { stage: "intake_item", status: "done", detail: { items: 2 } },
            { stage: "capture_obsidian", status: "skipped", detail: {} },
            { stage: "dispatch_retry", status: "failed", detail: { target: "notion" } },
          ],
        }),
      })],
    });

    render(<App />);
    await userEvent.click(await screen.findByText(/Run diagnostics/));

    expect(screen.getByRole("cell", { name: "intake_item" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "skipped" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "failed" })).toBeInTheDocument();
    // Empty detail is stated, not omitted.
    expect(screen.getAllByRole("cell", { name: "none" }).length).toBeGreaterThan(0);
  });

  it("renders the durable terminal report once the run reaches a terminal result", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({ pending: null, terminal_result: "complete" }),
        operation: { state: "idle", revision: 4 },
      })],
      report: runReport(),
    });

    render(<App />);
    await userEvent.click(await screen.findByText(/Run diagnostics/));

    expect(await screen.findByText("Terminal report")).toBeInTheDocument();
    expect(screen.getByText("Stage ledger")).toBeInTheDocument();
    expect(screen.getByText("vault/note.md")).toBeInTheDocument();
    // Empty groups read as none rather than disappearing.
    const discrepancies = screen.getByText("Discrepancies").closest("section");
    expect(within(discrepancies as HTMLElement).getByText("none")).toBeInTheDocument();
  });

  it("does not call a run complete while a failure is outstanding", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: null,
          terminal_result: "failed",
          last_error: { stage: "dispatch_retry", message: "target unreachable", retryable: true },
        }),
      })],
      report: runReport({ terminal_result: "failed", failed_from: "dispatch_retry" }),
    });

    render(<App />);

    await screen.findByText("dispatch_retry failed");
    expect(screen.queryByText("Ingestion complete")).not.toBeInTheDocument();
    expect(screen.getByText(/The run finished as/)).toBeInTheDocument();
  });
});

describe("an unsupported legal action", () => {
  it("fails loudly, blocks mutation, and is exposed in Run diagnostics", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: bookPending({ allowed_actions: ["confirm", "escalate"] }),
        }),
      })],
    });

    render(<App />);

    const surface = await screen.findByRole("region", { name: "Failure details" });
    expect(within(surface).getByText("Unsupported action contract")).toBeInTheDocument();
    // Named in both the message and the facts, so the action is never a mystery.
    expect(within(surface).getAllByText(/escalate/).length).toBeGreaterThan(0);

    // The known action is still shown, but nothing may be submitted.
    expect(screen.getByRole("button", { name: /Confirm identity/ })).toBeDisabled();

    await userEvent.click(await screen.findByText(/Run diagnostics/));
    const contract = screen.getByText("Action contract").closest("section");
    expect(within(contract as HTMLElement).getByText("book_identity")).toBeInTheDocument();
    expect(within(contract as HTMLElement).getByText("escalate")).toBeInTheDocument();
  });

  it("reports no contract problem when every returned action is supported", async () => {
    fakeGateway({ snapshots: [snapshot({ view: view({ pending: bookPending() }) })] });

    render(<App />);
    await userEvent.click(await screen.findByText(/Run diagnostics/));

    expect(screen.getByText("Every action the coordinator returned is supported."))
      .toBeInTheDocument();
    expect(screen.queryByText("Unsupported action contract")).not.toBeInTheDocument();
  });
});

describe("cleanup adapter", () => {
  it("dispatches to CleanupReview, never the generic JSON fallback", async () => {
    fakeGateway({ snapshots: [snapshot({ view: view({ pending: cleanupPending() }) })] });
    render(<App />);

    expect(await screen.findByText("Abbreviation review")).toBeInTheDocument();
    expect(document.querySelector(".evidence-json")).not.toBeInTheDocument();
    // Cleanup has no "approve" action; that vocabulary belongs to other adapters.
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
  });

  it("renders only the actions the coordinator returned", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({ pending: cleanupPending({ allowed_actions: ["apply_once", "skip"] }) }),
      })],
    });
    render(<App />);

    expect(await screen.findByRole("button", { name: /Apply once/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Skip/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Apply \+ remember/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Continue to approval/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Next/ })).not.toBeInTheDocument();
  });

  it("fails loudly on an action outside cleanup's own contract", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({ pending: cleanupPending({ allowed_actions: ["apply_once", "merge"] }) }),
      })],
    });
    render(<App />);

    const surface = await screen.findByRole("region", { name: "Failure details" });
    expect(within(surface).getByText("Unsupported action contract")).toBeInTheDocument();
    expect(within(surface).getAllByText(/merge/).length).toBeGreaterThan(0);
  });

  it("Shift+Enter never submits a cleanup decision -- it stays reserved for final approval", async () => {
    const gateway = fakeGateway({ snapshots: [snapshot({ view: view({ pending: cleanupPending() }) })] });
    render(<App />);
    await screen.findByText("Abbreviation review");

    await userEvent.keyboard("{Shift>}{Enter}{/Shift}");

    expect(gateway.called("/run/decision")).toBe(false);
  });

  it("Enter submits the phase's primary decision (C8-C6)", async () => {
    const gateway = fakeGateway({ snapshots: [snapshot({ view: view({ pending: cleanupPending() }) })] });
    render(<App />);
    await screen.findByText("Abbreviation review");

    await userEvent.keyboard("{Enter}");

    await waitFor(() => expect(gateway.called("/run/decision")).toBe(true));
  });

  it("shortcuts stay inactive while typing in the mapping form", async () => {
    const gateway = fakeGateway({ snapshots: [snapshot({ view: view({ pending: cleanupPending() }) })] });
    render(<App />);
    const shorthand = await screen.findByLabelText(/^Shorthand$/);

    await userEvent.click(shorthand);
    await userEvent.keyboard("{Enter}");

    expect(gateway.called("/run/decision")).toBe(false);
  });

  it("previews exact matches and submits the human-entered expansion for Apply once", async () => {
    const gateway = fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: cleanupPending({}, {
            authoritative_working_text: "Talk w/ me; write w/ care.",
          }),
        }),
      })],
    });
    render(<App />);

    expect(await screen.findByText(/2 exact matches in this document/)).toBeInTheDocument();
    const expansion = screen.getByLabelText(/^Expansion$/);
    await userEvent.clear(expansion);
    await userEvent.type(expansion, "along with");
    await userEvent.click(screen.getByRole("button", { name: /Apply once/ }));

    await waitFor(() => expect(gateway.called("/run/decision")).toBe(true));
    const decisionCall = gateway.fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/run/decision"));
    const body = JSON.parse(String(decisionCall?.[1]?.body)) as { payload: Record<string, unknown> };
    expect(body.payload).toMatchObject({
      shorthand: "w/",
      expansion: "along with",
      case_sensitive: true,
    });
  });

  it("shows the applied replacement, not the original text, once an occurrence is decided", async () => {
    fakeGateway({
      snapshots: [snapshot({
        view: view({
          pending: cleanupPending({}, {
            occurrence: {
              occurrence_id: "abbr-p0-5-7-1",
              ordinal: 1,
              total: 1,
              passage_index: null,
              base_start: 5,
              base_end: 7,
              current_start: 5,
              current_end: 7,
              original_text: "w/",
              proposed_text: "with",
              context_before: "Talk ",
              context_after: " me soon.",
              before_sentence: "",
              after_sentence: "",
              current_decision: "apply_once",
              mapping_id: "mapping-1",
              proposal_source: "mapping:mapping-1",
            },
          }),
        }),
      })],
    });
    render(<App />);

    const sentence = await screen.findByRole("status");
    expect(sentence).toHaveTextContent("Talk with me soon.");
    expect(sentence).not.toHaveTextContent("w/");
  });

  it("blocks a second submit while an earlier cleanup decision's confirmation is still pending", async () => {
    const gateway = fakeGateway({ snapshots: [snapshot({ view: view({ pending: cleanupPending() }) })] });
    render(<App />);
    const applyOnce = await screen.findByRole("button", { name: /Apply once/ });

    await userEvent.click(applyOnce);
    await waitFor(() => expect(gateway.called("/run/decision")).toBe(true));

    // The queued snapshot never advances past this point, so the operation
    // reads idle again while the confirming interaction_revision bump never
    // arrives -- exactly the gap between "accepted" and "confirmed". The
    // same button, for the same still-pending item, must stay disabled
    // through it (section 9.1).
    await waitFor(() => expect(screen.getByRole("button", { name: /Apply once/ })).toBeDisabled());
  });

  it("shows the unavailable checker distinctly from an empty phase", async () => {
    fakeGateway({ snapshots: [snapshot({ view: view({ pending: cleanupUnavailablePending() }) })] });
    render(<App />);

    expect(await screen.findByText("Spelling checker unavailable")).toBeInTheDocument();
    expect(screen.getByText("spelling gateway call failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
    expect(screen.queryByText(/No further/)).not.toBeInTheDocument();
  });
});

describe("confirmed success", () => {
  const approving = () => snapshot({
    view: view(),
    operation: { state: "idle", revision: 3 },
  });

  async function approveHighlight() {
    const approve = await screen.findByRole("button", { name: /Approve highlight/ });
    await userEvent.click(approve);
  }

  it("does not celebrate on the 202; it waits for the confirming snapshot", async () => {
    const gateway = fakeGateway({ snapshots: [approving()] });

    render(<App />);
    await approveHighlight();

    // Accepted only. The envelope must not have flown.
    expect(screen.queryByTestId("envelope-flight")).not.toBeInTheDocument();

    gateway.setSnapshots([snapshot({
      view: view({ pending: null, terminal_result: "complete" }),
      operation: { state: "idle", revision: 4 },
    })]);

    expect(await screen.findByTestId("envelope-flight")).toBeInTheDocument();
  });

  it("does not celebrate when the coordinator failed after accepting", async () => {
    const gateway = fakeGateway({ snapshots: [approving()] });

    render(<App />);
    await approveHighlight();

    gateway.setSnapshots([snapshot({
      view: view({ pending: null }),
      operation: { state: "failed", name: "decision", error: "the vault is read-only", revision: 3 },
    })]);

    await screen.findByText("decision failed");
    expect(within(failureSurface()).getByText("the vault is read-only")).toBeInTheDocument();
    expect(screen.queryByTestId("envelope-flight")).not.toBeInTheDocument();
  });

  it("does not celebrate on a revision that does not match the submission", async () => {
    const gateway = fakeGateway({ snapshots: [approving()] });

    render(<App />);
    await approveHighlight();

    gateway.setSnapshots([snapshot({
      view: view({ pending: null }),
      operation: { state: "idle", revision: 9 },
    })]);

    await waitFor(() => expect(screen.getByText(/Draft retained/)).toBeInTheDocument());
    expect(screen.queryByTestId("envelope-flight")).not.toBeInTheDocument();
  });

  it("does not celebrate while the same item is still pending", async () => {
    const gateway = fakeGateway({ snapshots: [approving()] });

    render(<App />);
    await approveHighlight();

    gateway.setSnapshots([snapshot({
      view: view(),
      operation: { state: "idle", revision: 4 },
    })]);

    await waitFor(() =>
      expect(screen.getByText(/image-1 is still awaiting a decision/)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("envelope-flight")).not.toBeInTheDocument();
  });

  it("never carries a rejected submission forward to a later unrelated success", async () => {
    const gateway = fakeGateway({
      snapshots: [approving()],
      decide: { kind: "error", status: 409, detail: "another coordinator operation is in flight" },
    });

    render(<App />);
    await approveHighlight();

    await screen.findByText("another coordinator operation is in flight");
    expect(screen.queryByTestId("envelope-flight")).not.toBeInTheDocument();

    // An unrelated operation now completes. The stale arming must not fire.
    gateway.setSnapshots([snapshot({
      view: view({ pending: null, terminal_result: "complete" }),
      operation: { state: "idle", revision: 4 },
    })]);
    await new Promise((resolve) => setTimeout(resolve, 1700));
    expect(screen.queryByTestId("envelope-flight")).not.toBeInTheDocument();
  });
});

describe("draft lifecycle", () => {
  const key = draftKey("run-1", "image-1");

  it("retains the draft when the submission is rejected", async () => {
    fakeGateway({
      snapshots: [snapshot({ operation: { state: "idle", revision: 3 } })],
      decide: { kind: "error", status: 412, detail: "stale decision revision 3; current revision is 4" },
    });

    render(<App />);
    const textarea = await screen.findByLabelText("Final text");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "My careful edit");
    await userEvent.click(screen.getByRole("button", { name: /Approve highlight/ }));

    await screen.findByText("stale decision revision 3; current revision is 4");
    expect(sessionStorage.getItem(key)).toContain("My careful edit");
  });

  it("clears the draft only after the matching decision is confirmed", async () => {
    const gateway = fakeGateway({
      snapshots: [snapshot({ operation: { state: "idle", revision: 3 } })],
    });

    render(<App />);
    const textarea = await screen.findByLabelText("Final text");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "My careful edit");
    await userEvent.click(screen.getByRole("button", { name: /Approve highlight/ }));

    // Accepted, not settled: the edit is still safe.
    expect(sessionStorage.getItem(key)).toContain("My careful edit");

    gateway.setSnapshots([snapshot({
      view: view({ pending: null, terminal_result: "complete" }),
      operation: { state: "idle", revision: 4 },
    })]);

    await waitFor(() => expect(sessionStorage.getItem(key)).toBeNull());
    expect(screen.getByText(/Draft cleared after confirmed success/)).toBeInTheDocument();
  });

  it("shows a diagnostic and falls back to backend text when storage is corrupt", async () => {
    sessionStorage.setItem(key, "{not json");
    fakeGateway({ snapshots: [snapshot()] });

    render(<App />);

    expect(await screen.findByText("Saved local edits could not be restored"))
      .toBeInTheDocument();
    // The app still works, showing the coordinator's own text.
    expect(await screen.findByLabelText("Final text"))
      .toHaveValue("We become what we notice.");
  });

  it("reconciles an accepted-but-unsettled submission found after a refresh", async () => {
    sessionStorage.setItem(key, JSON.stringify({
      value: [{ index: 0, ocr_text: "o", edited_text: "restored edit" }],
      pending: {
        runId: "run-1",
        itemId: "image-1",
        adapter: "image_ocr",
        action: "approve",
        submittedRevision: 3,
      },
    }));

    fakeGateway({
      snapshots: [snapshot({
        view: view({ pending: null, terminal_result: "complete" }),
        operation: { state: "idle", revision: 4 },
      })],
      report: runReport(),
    });

    render(<App />);

    // The submission is recognised as its own, confirmed, and settled.
    await waitFor(() => expect(sessionStorage.getItem(key)).toBeNull());
    expect(await screen.findByTestId("envelope-flight")).toBeInTheDocument();
  });
});
