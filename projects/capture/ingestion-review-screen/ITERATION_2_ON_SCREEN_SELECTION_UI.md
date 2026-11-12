# Iteration 2 — On-Screen Selection UI (T45, Part 1 of 3)

| Field | Value |
|---|---|
| **Status** | **Parked — do not build now** |
| **Owner when un-parked** | `/ingestion` route in the unified React AI OS shell |
| **Consumes later** | A typed draft/capture API defined by Part 2 |
| **Must not own** | Durable storage, pipeline stages, coordinator recovery |

## Outcome

Provide one clear interaction for selecting material already visible on the
computer. The person can correct mistakes before anything is approved or sent
to ingestion.

This document defines behavior, not final styling or implementation. When
un-parked, begin with an isolated prototype using the unified React shell's
stack and shared components. This legacy folder is reference material, not the
production home. Do not create another build/dev server or wire the prototype
to production storage or the pipeline.

## Two acquisition experiences

### Direct selectable text

For an article or document whose text is available directly:

- preserve the exact selected text;
- show a configurable amount of surrounding text above and below it;
- allow the selection and context boundary to be corrected;
- retain the visible source title/location supplied by the acquisition layer;
  and
- avoid OCR.

This may later be implemented inside a browser page, through a browser
extension, or through another document-aware integration. The prototype must
not assume one option before the capture-mechanism comparison is complete.

### Pixel selection

For images, scans, graphs, canvases, video frames, or inaccessible text:

- display one supplied screenshot or captured parent image;
- draw one or more arbitrary rectangles;
- move and resize a rectangle after drawing it;
- delete an accidental rectangle easily;
- preserve selections when zooming or panning;
- clearly distinguish the active rectangle from saved rectangles; and
- classify each rectangle as text or a retained visual. A later vocabulary may
  distinguish image, graph, table, and equation.

Text rectangles can request OCR. Visual rectangles retain their pixels and must
not be silently converted into text-only records.

## Required review interaction

Before approval, the screen shows:

- the parent source or screenshot;
- every selection overlaid on that parent;
- selected text separately from surrounding context;
- original OCR and corrected text when OCR was used;
- acquisition method and honest provenance summary;
- visible warnings, including missing permission or OCR failure; and
- Save draft, Approve, and Delete/Discard actions with unambiguous scope.

Several selections from one parent remain independent. Editing or deleting one
must not alter the others.

## Mistake recovery

- A tiny or empty rectangle is rejected with an immediate explanation.
- Escape cancels the rectangle currently being drawn.
- Delete removes only the selected rectangle and requires confirmation if it
  already contains corrected text.
- Undo/redo applies only to the unapproved local editing session unless Part 2
  later defines a durable edit history.
- Approval is disabled while a save is in flight or while any required field
  is invalid.
- Browser refresh reloads the durable draft from Part 2; frontend memory alone
  is never presented as saved work.

## States that must be designed

- no source selected;
- acquiring source;
- permission required/denied;
- source ready with no rectangles;
- drawing, resizing, moving, and deleting;
- OCR pending, successful, low-confidence, or failed;
- unsaved edits, saving, saved, save failed;
- duplicate warning returned by Part 2;
- approval pending, approved, or admission failed; and
- unavailable/changed source.

Loading, failure, empty, keyboard-focus, and narrow-screen states are first
class behavior—not polish to add afterward.

## Interaction and accessibility requirements

- Every pointer action has a keyboard-accessible equivalent or an accessible
  form-based fallback for rectangle coordinates.
- Focus remains visible and moves predictably when rectangles are created or
  deleted.
- Selection identity is conveyed by labels/patterns as well as color.
- Text and controls meet WCAG AA contrast.
- Zoom must not change saved natural-image coordinates.
- The layout must handle long OCR text, many selections, and small screens
  without hiding approval or error information.

## Historical reference

`Page Scanner copy/static/review.js` around `submitDragBox()` demonstrates
rubber-band drawing, display-to-natural-image coordinate conversion, and
several rectangles on one image. `Page Scanner copy/server.py::api_ocr_box()`
demonstrates cropped OCR.

Reuse the interaction lessons, not the old visual design or direct API shape.
The production frontend uses the authenticated `/api/ingestion/...` router and
OpenAPI-generated/shared types from Pydantic models; it never calls
`pipeline.capture()` or maintains a handwritten duplicate contract.

## First deliverable when un-parked

An isolated, reviewable selector prototype with:

1. a supplied test screenshot;
2. draw, select, move, resize, and delete;
3. multiple independent rectangles;
4. text-versus-visual classification;
5. editable selected text and visible context; and
6. realistic empty, loading, OCR-failure, save-failure, and permission states.

No persistence or ingestion integration is part of that first deliverable.
