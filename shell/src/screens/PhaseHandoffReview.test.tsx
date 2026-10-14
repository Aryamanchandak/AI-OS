import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PhaseHandoffPending } from "../api/client";
import { phaseHandoffPending } from "../test/factories";
import { PhaseHandoffReview } from "./PhaseHandoffReview";

function renderReview(overrides: Partial<PhaseHandoffPending["payload"]> = {}) {
  const pending = phaseHandoffPending({
    payload: { ...phaseHandoffPending().payload, ...overrides },
  } as never) as PhaseHandoffPending;
  const submit = vi.fn();
  const onUnsupported = vi.fn();
  render(
    <PhaseHandoffReview pending={pending} busy={false} submit={submit} onUnsupported={onUnsupported} />,
  );
  return { submit, onUnsupported };
}

describe("PhaseHandoffReview", () => {
  it("renders all six typed intake counts as labelled figures", () => {
    renderReview({
      discovered: 5, published: 3, discarded: 1, retake: 1, duplicate: 0, failed: 0,
      note_paths: [],
    });

    expect(screen.getByText("Discovered")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Published")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders note_paths as a readable list, or 'none' when empty", () => {
    renderReview({ note_paths: ["vault/a.md", "vault/b.md"] });
    expect(screen.getByText("vault/a.md")).toBeInTheDocument();
    expect(screen.getByText("vault/b.md")).toBeInTheDocument();
  });

  it("states 'none' rather than disappearing when there are no notes", () => {
    renderReview({ note_paths: [] });
    expect(screen.getByText("none")).toBeInTheDocument();
  });

  it("submits continue and stop with an empty payload through ActionBar", async () => {
    const { submit } = renderReview();

    await userEvent.click(screen.getByRole("button", { name: /Continue into knowledge work/ }));
    expect(submit).toHaveBeenCalledWith("continue", {});

    await userEvent.click(screen.getByRole("button", { name: /Stop/ }));
    expect(submit).toHaveBeenCalledWith("stop", {});
  });

  it("states plainly that Stop completes the run rather than pausing it", () => {
    renderReview();
    expect(screen.getByText(/Stop completes this run/)).toBeInTheDocument();
  });

  it("treats the coordinator's empty item_id as the run-level pending, not a missing item", () => {
    const pending = phaseHandoffPending() as PhaseHandoffPending;
    expect(pending.item_id).toBe("");
    render(
      <PhaseHandoffReview pending={pending} busy={false} submit={vi.fn()} onUnsupported={vi.fn()} />,
    );
    expect(screen.getByText("Continue into knowledge work?")).toBeInTheDocument();
  });
});
