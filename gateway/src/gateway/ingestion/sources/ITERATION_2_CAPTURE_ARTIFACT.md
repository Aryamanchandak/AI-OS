# Iteration 2 — Durable Capture Artifact (T45, Part 2 of 3)

| Field | Value |
|---|---|
| **Status** | **Parked — do not build now** |
| **Owner** | Ingestion source/capture layer |
| **Receives later** | Drafts and approval intent from the frontend |
| **Produces later** | One durable approved capture for coordinator admission |
| **Must not own** | UI interaction or coordinator stage transitions |

## Outcome

Define and persist one truthful capture artifact before ingestion starts. A
capture contains one parent source and one or more independent selections.
Closing the frontend or Python process must not lose saved work.

This is a future contract plan. It does not authorize schema or storage changes.

## Artifact shape to design

### Parent capture

- stable capture identifier;
- capture timestamp;
- acquisition method: direct selectable text, supplied image, or platform
  pixel capture;
- parent text and/or an immutable parent image reference;
- parent image hash, pixel dimensions, and display scale where applicable;
- source title/location and application/window/display identity when safely
  available;
- explicit statement of what was and was not captured, especially off-screen
  context; and
- draft, approved, admitted, or failed lifecycle state with timestamps.

### Each selection

- stable selection identifier and parent capture identifier;
- kind: text or retained visual, with a future T59 subtype if approved;
- exact selected text and separately stored visible context;
- corrected text plus original OCR output when OCR was used;
- character offsets for direct text when available;
- selected and context pixel rectangles for image-based capture;
- OCR engine/model/version and confidence details;
- user edits and approval state; and
- retained crop reference/hash for every visual selection.

Pixel rectangles must not be overloaded into character-offset fields. An
initial implementation may serialize a versioned typed metadata object, but it
must not emit unvalidated ad-hoc keys.

## Reuse the existing text-selection contract

`src/ingestion/models.py` already defines `CaptureRequest` and `UserSelection`.
They support one or several exact text selections, context, parent references,
and character offsets. `src/ingestion/parsing.py` preserves
`boundary_origin="user_selection"`, meaning the selected text becomes the
highlight exactly as chosen rather than being split again by a model.

`src/ingestion/store.py` already persists these selection payloads, and
`src/ingestion/sources/obsidian.py::capture_book_highlights()` demonstrates one
parent with several independent child highlights.

The future artifact should adapt into that landed contract for text. It still
needs a typed screen-specific provenance and visual-artifact layer.

## Durable draft and restart behavior

- Save the parent before or atomically with its first selection.
- A successful Save draft returns durable identifiers and a revision.
- Updates use revision checks so two tabs cannot silently overwrite each other.
- Approval is durable and idempotent.
- A crash during parent-image or crop writing cannot expose a falsely complete
  artifact.
- On restart, the frontend can list/reopen its saved but unapproved drafts.
- An approved artifact remains discoverable until Part 3 durably admits it.
- Admission failure does not erase the artifact or its approval.

The physical storage location and database schema must be chosen in the future
design pass, consistent with the project's approved Database layout.

## Duplicate behavior to design

Duplicate detection is a warning/identity problem, not permission to merge
records silently. Candidate evidence may include:

- parent image or normalized direct-text hash;
- source identity;
- selected text;
- selected/context rectangles; and
- capture time.

The design must distinguish an accidental repeat from two intentional
highlights with identical wording. The user or an explicit policy makes the
final keep/discard choice.

## Visual selections and T59

For images, graphs, tables, and equations:

- retain the original selected pixels as an immutable artifact;
- allow OCR text or a later caption to be attached;
- never replace the pixels with OCR text merely because OCR succeeded; and

- preserve enough parent/rectangle provenance to show where the crop came
  from.

T59 must still decide permanent storage, projection, retrieval, and whether
different visual subtypes behave differently downstream. Part 3 must not admit
visual selections as ordinary text highlights until that is settled.

## Contract boundary

The frontend creates and edits drafts through this layer. This layer validates
and saves them. It does not call the ingestion pipeline. After approval it
exposes one durable artifact for the coordinator-owned Part 3 seam.

## First design work when un-parked

1. Choose the durable physical home and transactional write strategy.
2. Write the versioned parent/selection schema, including visual crops.
3. Define create, update, reopen, approve, discard, and admission-status APIs.
4. Settle duplicate warning behavior.
5. Settle T59's durable visual semantics.
6. Map approved text selections into existing `CaptureRequest`/
   `UserSelection` without losing provenance.
