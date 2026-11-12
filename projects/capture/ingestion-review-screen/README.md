# Ingestion Review Screen — Legacy Migration Reference

> **Superseded 2026-08-13:** per
> `AI Code/Constitution/UI ARCHITECTURE.MD`, this standalone vanilla screen is
> not the production UI home. Production ingestion belongs at `/ingestion` in
> the one React AI OS shell, backed by authenticated `/api/ingestion/...` routes
> in the one FastAPI gateway. The files here remain parity/migration reference
> material until that route is verified, then the standalone entry point is
> retired. Do not add new production UI behavior here.

The one screen through which the ingestion pipeline runs.

Books photographed under a camera, PDFs, Word documents, and Markdown files are
dropped into a folder. The pipeline reads them, turns them into notes in the
Obsidian vault, extracts concepts and claims from them, and files those into the
knowledge graph. It stops and asks a person whenever it is not confident. **This
unified shell's `/ingestion` route is what that person will use.**

Everything here is legacy reference material. Nothing here decides what the
pipeline does, and new UI work belongs in the unified React shell.

```
AI Code/
├── frontend/
│   └── Ingestion Review Screen/     ← you are here: how it looks
└── ingestion-pipeline/
    └── merged-ingestion/
        ├── cockpit/server.py        ← the API this screen talks to
        └── src/ingestion/           ← how things actually get ingested
```

## Legacy preview only

The backend serves this folder, so there is one command and one URL:

```bash
cd "AI Code/ingestion-pipeline/merged-ingestion"
PYTHONPATH=src bash scripts/run.sh python -m cockpit.server
```

Then open **http://127.0.0.1:8765**. This is a temporary legacy preview, not
the constitutional production command or URL.

The lack of a build step describes this legacy implementation only. The target
is the existing React shell and its normal toolchain; do not use this paragraph
to justify a separate vanilla production app.

The backend finds this folder by walking up to the `AI Code` root and looking
for `frontend/Ingestion Review Screen/`. If you rename or move it, either fix
the name or set `INGESTION_FRONTEND_ROOT` to the new path. A missing folder is a
loud startup error, not a blank page.

### Designing without running the pipeline

Running the real pipeline means real OCR, real vault writes, and real model
calls. To work on the look instead, run the fixture server — same screen, fake
coordinator, no side effects:

```bash
cd "AI Code/ingestion-pipeline/merged-ingestion"
PYTHONPATH=src bash scripts/run.sh python -m uvicorn tests.cockpit_preview:app --port 8765
```

It opens on a book-identity decision; confirming moves to an image/OCR decision;
the next decision completes the run. Fixtures live in
`merged-ingestion/tests/cockpit_preview.py` — add more there when you want to
style a state that is hard to reach for real.

## The one-screen rule

There is one URL and one frame. The user never navigates to a second review
application, never picks a queue, never chooses a stage. The frame stays put and
only its middle swaps:

```
┌──────────────────────────────────────────────────────────────────┐
│ Run · health · read-only progress                                │
├────────────────────────────────┬─────────────────────────────────┤
│ Evidence                       │ Current decision                │
│ image, text, source, context   │ fields + only the legal actions │
│ or automatic-stage status      │ for the current item            │
├────────────────────────────────┴─────────────────────────────────┤
│ Save/error feedback · run detail · keyboard help                 │
└──────────────────────────────────────────────────────────────────┘
```

The stage rail is visible but never clickable. Iteration 1 has no Back button,
no history, no reopening committed work, no bulk approval.

## What this screen has to render

The backend answers `GET /api/run` with a snapshot. When it is waiting on a
person, `view.pending.adapter` names which body to show:

| `pending.adapter` | What the person is deciding |
|---|---|
| `book_identity` | Is this the right book? Confirm, or correct the title/author |
| `image_ocr` | Are these the right highlighted passages off this page photo? |
| `text_file` | Is this extracted Markdown correct? |
| `phase_handoff` | Everything is published — continue into knowledge processing, or stop |
| `knowledge_proposal` | Is this extracted concept/claim/relation right? Approve, edit, or reject |

When nothing is pending, the same frame shows automatic progress, a failure with
its exact error, or the completed run's report.

## The line you must not cross

The rule is: **this folder owns what it looks like and how it behaves in the
browser. The pipeline owns what actually happens.**

Yours, change freely:

- layout, typography, colour, spacing, motion, responsive behaviour
- how forms feel, how drafts are held before submission, validation messages
- loading, empty, error, and success presentation
- keyboard shortcuts and accessibility

Not yours, ever:

- deciding what stage comes next, or skipping one
- keeping a second copy of the queue, run position, or decisions
- showing an action that is not in `pending.allowed_actions` — the backend says
  what is legal for the current item, and only those buttons may appear
- touching the vault, the databases, or any file path directly
- inventing progress percentages for work the backend has not reported

"How it's saved" means the draft in the form before Save is pressed. The
*durable* record of a decision belongs to the pipeline — the backend writes it
to `.book.json`, `processed.db`, or `ingestion.db`. A refresh mid-decision should
lose nothing local; a refresh must never re-run a decision or start a second run.

## Legacy backend contract

The unprefixed endpoints below document the migration source only. The target
endpoints live below `/api/ingestion/...`, use gateway bearer auth, and derive
frontend types from backend Pydantic/OpenAPI models rather than a handwritten
JavaScript contract. See the rewritten Component 6 connection plan.

Six endpoints, all same-origin, all relative paths:

| | |
|---|---|
| `GET /api/run` | the snapshot: latest view + operation state. Poll this |
| `POST /api/run/start` | start or resume. Once per app start, never on refresh |
| `POST /api/run/decision` | submit exactly one decision |
| `POST /api/run/retry` | retry a failed stage — only when `view.last_error.retryable` |
| `GET /api/evidence/{run_id}/{item_id}` | the current page photo |
| `GET /api/run/{run_id}/report` | the finished run's report |

`GET /api/meta` lists the contract version and supported adapters, and
`/openapi.json` is the machine-readable version of the whole surface.

**A decision is accepted, not completed.** `POST /api/run/decision` returns
`202` immediately and the real work (OCR, publishing, extraction) can take
minutes. Keep polling `/api/run` until `operation.state` leaves `submitting` and
`operation.revision` advances — only then clear the local draft. A `409` means
another operation is already in flight.

Identities are copied from the current view, never constructed here:

```javascript
{
  run_id: view.run_id,
  item_id: view.pending.item_id,   // "" for phase_handoff — deliberate
  gate:    view.pending.gate,
  action,                           // must be in pending.allowed_actions
  payload, resolver, note
}
```

Evidence URLs expire. Once the coordinator advances, the old image 404s — that
is the authorization model working, not a bug.

## Files

| File | What it is |
|---|---|
| `index.html` | the shell — header, `#app`, toast, screen-reader announcer |
| `review.css` | all styling |
| `review.js` | polling, drafts, and one render function per adapter |
| `ITERATION_2_ON_SCREEN_SELECTION_UI.md` | **parked** — the future on-screen selection UI (T45). Do not build |

`review.js` is deliberately one plain file with no imports. If it outgrows that,
splitting it is your call; keeping the API calls in one place at the top and the
adapter renderers below is the only structure worth preserving.

## Where the decisions behind this are written down

- `ingestion-pipeline/integration/to_do_plans/page_scanner_absorption/component_6/frontend_connection_plan.md`
  — the contract, the ownership split, and why each piece sits where it does
- `.../component_6/component_6.md` — what this screen must do and how it is tested
