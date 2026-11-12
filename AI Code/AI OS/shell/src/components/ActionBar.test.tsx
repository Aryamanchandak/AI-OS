import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ActionBar, resolveActions, type ActionDescriptor } from "./ActionBar";

const descriptors: ActionDescriptor[] = [
  { action: "approve", label: "Approve", tone: "primary", buildPayload: () => ({ text: "final" }) },
  { action: "retake", label: "Retake", tone: "danger", buildPayload: () => ({}) },
  { action: "discard", label: "Discard", buildPayload: () => ({}) },
];

function renderBar(allowed: string[], overrides: Partial<{ busy: boolean }> = {}) {
  const submit = vi.fn();
  const onUnsupported = vi.fn();
  render(
    <ActionBar
      adapter="image_ocr"
      allowedActions={allowed}
      descriptors={descriptors}
      busy={overrides.busy ?? false}
      submit={submit}
      onUnsupported={onUnsupported}
    />,
  );
  return { submit, onUnsupported };
}

describe("resolveActions", () => {
  it("renders in the adapter's order regardless of the coordinator's order", () => {
    const { rendered } = resolveActions(["discard", "approve"], descriptors);
    expect(rendered.map((entry) => entry.action)).toEqual(["approve", "discard"]);
  });

  it("names actions the adapter cannot serialize", () => {
    const { unsupported } = resolveActions(["approve", "escalate"], descriptors);
    expect(unsupported).toEqual(["escalate"]);
  });
});

describe("ActionBar", () => {
  it("renders only the actions the coordinator returned", () => {
    renderBar(["approve", "discard"]);
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discard" })).toBeInTheDocument();
    // An action the coordinator did not return is never offered.
    expect(screen.queryByRole("button", { name: "Retake" })).not.toBeInTheDocument();
  });

  it("submits the adapter's payload for the chosen action", async () => {
    const { submit } = renderBar(["approve"]);
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(submit).toHaveBeenCalledWith("approve", { text: "final" });
  });

  it("raises a contract failure and blocks submission for an unknown legal action", async () => {
    const { onUnsupported, submit } = renderBar(["approve", "escalate"]);

    expect(onUnsupported).toHaveBeenCalledWith({
      adapter: "image_ocr",
      actions: ["escalate"],
    });
    // Nothing is silently omitted, and nothing may be submitted meanwhile.
    const approve = screen.getByRole("button", { name: "Approve" });
    expect(approve).toBeDisabled();
    await userEvent.click(approve);
    expect(submit).not.toHaveBeenCalled();
  });

  it("clears a previously raised contract failure when every action is known", () => {
    const { onUnsupported } = renderBar(["approve", "retake"]);
    expect(onUnsupported).toHaveBeenCalledWith(null);
  });

  it("disables every server action while an operation is in flight", () => {
    renderBar(["approve", "discard"], { busy: true });
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard" })).toBeDisabled();
  });
});
