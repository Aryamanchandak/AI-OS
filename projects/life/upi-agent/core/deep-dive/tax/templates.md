# `tax/templates.py`

**Lines:** 643

## Purpose

Holds the two full-page HTML applications for the tax module as Python string constants (`TRIAGE_HTML`, `SETTINGS_HTML`). There are no Python functions or classes. Both pages are single-page applications that communicate with the `/tax/api/*` endpoints via `fetch()` calls.

## `TRIAGE_HTML` — What the JavaScript Actually Does

The triage page is a single-item queue processor. It loads one payment at a time:

1. `init()` calls `loadSettings()` then `loadNext()`.
2. `loadSettings()` fetches `/tax/api/settings`; sets `currentMode`; renders the mode toggle; disables the AI mode option if no LLM endpoint is configured.
3. `loadNext()` fetches `/tax/api/queue?limit=1`; if empty shows "All caught up"; otherwise fetches `/tax/api/payment/{id}/context` and calls `renderCurrent()`.
4. `renderCurrent()` builds the card DOM: amount, date, counterparty, VPA, narration, raw_text, past classifications as pills, calendar events as pills, classifier suggestion (only shown when mode is `'ai'` and a bucket was suggested), bucket dropdown, Confirm/Skip buttons.
5. `onConfirm()`: if `retro_unclassified_count > 0`, shows the native `<dialog>` element asking whether to apply to all same-merchant rows. Either path calls `doClassify(bucket, applyRetro)`.
6. `doClassify()` POSTs to `/tax/api/payment/{id}/classify`, shows a toast, then calls `loadNext()`.
7. Mode toggle: clicking a label POSTs to `/tax/api/settings` to persist the mode change, then calls `renderCurrent()` to re-render the current card with or without the suggestion block.
8. Upload zone: supports drag-and-drop and file picker; POSTs to `/tax/upload`; on success calls `loadNext()`.

## `SETTINGS_HTML` — What the JavaScript Actually Does

A settings panel with two sections:

1. **Buckets section:** On load, `loadBuckets()` fetches `/tax/api/buckets` and renders each as an editable input (blur event saves rename via PATCH) with an archive/restore button. "Add" button POSTs a new bucket.
2. **Classification mode section:** On load, `loadSettings()` sets radio buttons and fills LLM endpoint/model fields. "Save" POSTs to `/tax/api/settings`. "Test connection" POSTs to `/tax/api/test_llm` and renders success/failure inline.

## Design Decisions

- The suggestion block in TRIAGE_HTML is only rendered when `currentMode === 'ai'` — checked client-side at render time. The server always returns a suggestion; the client decides whether to show it. This means the mode toggle re-renders the current card without a round-trip.
- The bucket dropdown pre-selects the suggested bucket. In AI mode the user can accept the suggestion by just clicking Confirm without touching the dropdown.

## Known Gaps / Risks

- **XSS risk:** `counterparty_name`, `counterparty_vpa`, `narration`, `raw_text`, and calendar event titles are interpolated directly into `innerHTML` strings without HTML escaping. A description containing `<script>alert(1)</script>` or an `<img onerror=...>` tag would execute in the browser. Lower severity for a local personal tool, but real.
- **`<dialog>` element browser support:** The native HTML `<dialog>` / `showModal()` pattern requires a polyfill in older browsers. No polyfill is included.
- **No error state on queue fetch failure:** If `/tax/api/queue` returns a non-200 status, `loadNext()` does not catch the error and the UI silently stops showing payments.
- **Bucket dropdown injection:** Bucket names are injected as `<option value="${b}">` without escaping. A bucket named `"><script>` would cause malformed HTML. The server-side 50-character limit mitigates but does not prevent HTML injection.
