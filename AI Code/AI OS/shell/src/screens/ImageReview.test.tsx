import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ImageOcrPending } from "../api/client";
import { imagePending } from "../test/factories";
import { ImageReview } from "./ImageReview";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubEvidence(response: Response | (() => Response)) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => (typeof response === "function" ? response() : response)),
  );
}

function renderReview(pending: ImageOcrPending) {
  const submit = vi.fn();
  const onUnsupported = vi.fn();
  const onDraftProblem = vi.fn();
  render(
    <ImageReview
      pending={pending}
      busy={false}
      submit={submit}
      onUnsupported={onUnsupported}
      onDraftProblem={onDraftProblem}
      token="test-token"
      runId="run-1"
    />,
  );
  return { submit, onUnsupported, onDraftProblem };
}

/** jsdom never actually decodes the <img>; the component reads naturalWidth/
 * naturalHeight off the load event's target, so a real dimension needs to be
 * forced onto the element before firing it. */
function fireImageLoaded(width: number, height: number) {
  const img = screen.getByAltText("Current source page");
  Object.defineProperty(img, "naturalWidth", { value: width, configurable: true });
  Object.defineProperty(img, "naturalHeight", { value: height, configurable: true });
  fireEvent.load(img);
}

describe("evidence image and overlay registration", () => {
  it("positions a passage overlay as a percentage of the real, loaded image dimensions", async () => {
    stubEvidence(new Response(new Blob(["image"]), { status: 200 }));
    const base = imagePending() as ImageOcrPending;
    const pending: ImageOcrPending = {
      ...base,
      payload: {
        ...base.payload,
        passages: [
          { index: 0, ocr_text: "x", edited_text: "x", bbox: [100, 200, 300, 400], min_conf: 0.9 },
        ],
      },
    };

    const { container } = render(
      <ImageReview
        pending={pending}
        busy={false}
        submit={vi.fn()}
        onUnsupported={vi.fn()}
        onDraftProblem={vi.fn()}
        token="test-token"
        runId="run-1"
      />,
    );
    await screen.findByAltText("Current source page");
    fireImageLoaded(1000, 2000);

    const box = container.querySelector(".passage-box") as HTMLElement;
    expect(box.style.left).toBe("10%");
    expect(box.style.top).toBe("10%");
    expect(box.style.width).toBe("30%");
    expect(box.style.height).toBe("20%");
  });

  it("shows the exact evidence error and never the loading text when the fetch is rejected", async () => {
    stubEvidence(new Response(JSON.stringify({ detail: "gone" }), { status: 404 }));
    renderReview(imagePending() as ImageOcrPending);

    expect(await screen.findByText("Image evidence is no longer current."))
      .toBeInTheDocument();
    expect(screen.queryByText("Loading current evidence…")).not.toBeInTheDocument();
    // No group/keyboard affordance for an image that never loaded.
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });
});

describe("zoom and pan", () => {
  it("Zoom in, Zoom out and Reset buttons are reachable and change the image transform", async () => {
    stubEvidence(new Response(new Blob(["image"]), { status: 200 }));
    renderReview(imagePending() as ImageOcrPending);
    await screen.findByAltText("Current source page");
    fireImageLoaded(1000, 1000);

    const wrap = document.querySelector(".image-wrap") as HTMLElement;
    const initialTransform = wrap.style.transform;

    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    await waitFor(() => expect(wrap.style.transform).not.toBe(initialTransform));
    const zoomedTransform = wrap.style.transform;

    await userEvent.click(screen.getByRole("button", { name: "Reset zoom and pan" }));
    await waitFor(() => expect(wrap.style.transform).not.toBe(zoomedTransform));
  });

  it("arrow keys pan and +/-/0 zoom/reset, scoped to the image stage", async () => {
    stubEvidence(new Response(new Blob(["image"]), { status: 200 }));
    renderReview(imagePending() as ImageOcrPending);
    await screen.findByAltText("Current source page");
    fireImageLoaded(1000, 1000);

    const stage = screen.getByRole("group", { name: /Arrow keys pan/ });
    const wrap = document.querySelector(".image-wrap") as HTMLElement;
    const initial = wrap.style.transform;

    stage.focus();
    fireEvent.keyDown(stage, { key: "+" });
    await waitFor(() => expect(wrap.style.transform).not.toBe(initial));
    const zoomed = wrap.style.transform;

    fireEvent.keyDown(stage, { key: "ArrowRight" });
    await waitFor(() => expect(wrap.style.transform).not.toBe(zoomed));
    const panned = wrap.style.transform;

    fireEvent.keyDown(stage, { key: "0" });
    await waitFor(() => expect(wrap.style.transform).not.toBe(panned));
  });

  it("has a visible, labelled focus target with keyboard instructions in its accessible name", async () => {
    stubEvidence(new Response(new Blob(["image"]), { status: 200 }));
    renderReview(imagePending() as ImageOcrPending);
    await screen.findByAltText("Current source page");
    fireImageLoaded(1000, 1000);

    const stage = screen.getByRole("group", {
      name: "Evidence image. Arrow keys pan, plus and minus zoom, 0 resets.",
    });
    expect(stage).toHaveAttribute("tabindex", "0");
  });
});

describe("Shift+Enter approval", () => {
  it("approves via Shift+Enter when focus is outside any input or textarea", async () => {
    stubEvidence(new Response(new Blob(["image"]), { status: 200 }));
    const { submit } = renderReview(imagePending() as ImageOcrPending);
    await screen.findByAltText("Current source page");

    fireEvent.keyDown(document, { key: "Enter", shiftKey: true });

    expect(submit).toHaveBeenCalledWith("approve", expect.objectContaining({
      passages: [{ index: 0, edited_text: "We become what we notice." }],
      page_number: 42,
    }));
  });

  it("does nothing on Shift+Enter while focus is in the passage textarea", async () => {
    stubEvidence(new Response(new Blob(["image"]), { status: 200 }));
    const { submit } = renderReview(imagePending() as ImageOcrPending);
    await screen.findByAltText("Current source page");

    const textarea = screen.getByLabelText("Final text");
    textarea.focus();
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });

    expect(submit).not.toHaveBeenCalled();
  });
});
