import { Image as ImageIcon, Send } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { ImageOcrPending, ImagePassage } from "../api/client";
import { ActionBar, type ActionDescriptor } from "../components/ActionBar";
import { AdapterFrame, Metric } from "../components/primitives";
import { PhotoStage, type PhotoBox } from "../components/PhotoStage";
import { readDraft, writeDraft } from "../drafts";
import { draftFailure, type Failure } from "../failures";
import { useEvidenceImage } from "../hooks/useEvidenceImage";
import type { AdapterProps } from "./types";

/** A draft is only usable if it still looks like this item's passage list. */
function isPassageList(value: unknown): value is ImagePassage[] {
  return Array.isArray(value) && value.every((item) => (
    typeof item === "object"
    && item !== null
    && typeof (item as ImagePassage).index === "number"
    && typeof (item as ImagePassage).edited_text === "string"
    && typeof (item as ImagePassage).ocr_text === "string"
  ));
}

/**
 * OCR must be checked against the photographed page and its stored bounding
 * boxes. The user edits the passage text and page, then approves; or requires a
 * retake; or discards the image.
 *
 * This view never clears its own draft. A 202 only means accepted, so draft
 * settlement is decided centrally once the backend confirms the decision.
 */
export function ImageReview({
  pending,
  busy,
  submit,
  onUnsupported,
  token,
  runId,
  onDraftProblem,
}: AdapterProps<ImageOcrPending> & {
  token: string;
  runId: string;
  onDraftProblem: (failure: Failure | null) => void;
}) {
  const { payload } = pending;
  const itemId = pending.item_id;

  // Restoring the draft is done once, defensively: corrupt storage must
  // produce a visible diagnostic and fall back to backend truth, never throw
  // during render and never reach the server.
  const [initial] = useState(() => {
    const stored = readDraft(runId, itemId, isPassageList);
    if (stored.status === "corrupt") {
      return { passages: payload.passages, problem: stored.reason };
    }
    return {
      // A record holding only a submission marker has no value to restore.
      passages: stored.status === "ok" && stored.record.value !== null
        ? stored.record.value
        : payload.passages,
      problem: null as string | null,
    };
  });

  const [passages, setPassages] = useState<ImagePassage[]>(initial.passages);
  const [page, setPage] = useState(String(payload.page_number ?? ""));
  const { imageUrl, imageError } = useEvidenceImage(token, runId, itemId);

  const boxes = useMemo<PhotoBox[]>(
    () => passages
      .filter((passage): passage is ImagePassage & { bbox: number[] } => passage.bbox !== null && passage.bbox !== undefined)
      .map((passage) => ({
        key: String(passage.index),
        bbox: passage.bbox as [number, number, number, number],
      })),
    [passages],
  );

  useEffect(() => {
    onDraftProblem(
      initial.problem ? draftFailure(runId, itemId, initial.problem) : null,
    );
  }, [initial.problem, itemId, onDraftProblem, runId]);

  useEffect(() => {
    // Preserve any accepted-but-unsettled submission recorded against this
    // draft, so a refresh can still reconcile it.
    const existing = readDraft(runId, itemId, isPassageList);
    writeDraft(runId, itemId, {
      value: passages,
      pending: existing.status === "ok" ? existing.record.pending : null,
    });
  }, [passages, runId, itemId]);

  const update = (index: number, value: string) => {
    setPassages((items) => items.map((item, itemIndex) => (
      itemIndex === index ? { ...item, edited_text: value } : item
    )));
  };

  const descriptors = useMemo<ActionDescriptor[]>(() => [
    {
      action: "approve",
      label: <>Approve highlight <Send size={17} /><kbd>⇧ Enter</kbd></>,
      tone: "primary",
      disabled: passages.every((item) => !item.edited_text.trim()),
      buildPayload: () => ({
        passages: passages.map((item) => ({
          index: item.index,
          edited_text: item.edited_text,
        })),
        page_number: page ? Number(page) : null,
      }),
    },
    { action: "retake", label: "Retake", tone: "danger", buildPayload: () => ({}) },
    { action: "discard", label: "Discard", buildPayload: () => ({}) },
  ], [page, passages]);

  const approve = useCallback(() => {
    const descriptor = descriptors[0];
    if (descriptor.disabled) return;
    if (!pending.allowed_actions.includes("approve")) return;
    submit("approve", descriptor.buildPayload());
  }, [descriptors, pending.allowed_actions, submit]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        event.shiftKey
        && event.key === "Enter"
        && !busy
        && target?.tagName !== "INPUT"
        && target?.tagName !== "TEXTAREA"
      ) {
        event.preventDefault();
        approve();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [approve, busy]);

  return (
    <AdapterFrame
      title="Review the highlight"
      eyebrow="Source evidence · final text"
      icon={<ImageIcon />}
      aside={
        <>
          <Metric
            label="OCR confidence"
            value={`${Math.round((1 - (payload.conf_ratio ?? 0)) * 100)}%`}
          />
          <Metric label="Blur" value={payload.blur_score ?? "Unknown"} />
          <Metric label="Glare" value={payload.glare_score ?? "Unknown"} />
        </>
      }
    >
      <div className="review-grid">
        <PhotoStage
          imageUrl={imageUrl}
          imageError={imageError}
          boxes={boxes}
          alt="Current source page"
          label="Evidence image"
        />
        <div className="passage-stack">
          {passages.map((passage, index) => (
            <article className="passage-card" key={passage.index}>
              <p className="eyebrow">Passage {index + 1}</p>
              <blockquote>{passage.ocr_text}</blockquote>
              <label>
                Final text
                <textarea
                  value={passage.edited_text}
                  onChange={(event) => update(index, event.target.value)}
                  rows={5}
                />
              </label>
            </article>
          ))}
        </div>
      </div>
      <label className="page-field">
        Page number
        <input inputMode="numeric" value={page} onChange={(event) => setPage(event.target.value)} />
      </label>
      <ActionBar
        adapter="image_ocr"
        allowedActions={pending.allowed_actions}
        descriptors={descriptors}
        busy={busy}
        submit={submit}
        onUnsupported={onUnsupported}
      />
    </AdapterFrame>
  );
}
