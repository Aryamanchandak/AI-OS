# Marginal

Marginal is a local-first Chromium extension for freezing web articles, highlighting
them in a stable reader, and projecting those highlights back onto the original page
only when the match is trustworthy.

The frozen document is authoritative. Highlight wrappers are disposable, every record
keeps four anchors, and an ambiguous live-page match is refused instead of guessed.

## Run it

```bash
npm install
npm run build
```

Then open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**,
and select the `dist` directory.

Use the Marginal toolbar button (or `Alt+Shift+M`) on an article page. A successful
Readability capture opens in the reader. If extraction is suspiciously short, Marginal
offers explicit selection, cleaned-body, and extracted-result fallbacks before saving.

## What is included

- M0–M3: canonical text, persistent highlights, notes, tags, undo, merge, export,
  forced re-anchoring, and drag/keyboard resize.
- M4: Readability extraction, DOMPurify allowlist sanitization, frozen capture, and
  unchanged-capture deduplication.
- M5: multi-document library search across metadata, quotes, notes, and tags; deletion;
  original-page links; complete Markdown and JSON downloads.
- M6: automatic overlay on matching original URLs, exact/context and fuzzy resolution,
  visible refusal counts, and one-click return to the frozen reader.
- M7: whole-library backup and validated restore, transactional storage hardening,
  accessible keyboard/dialog behavior, responsive reader chrome, and a permanent hostile
  document regression corpus.

All data is stored in extension-origin IndexedDB. There is no account, server, sync,
analytics, or network request after the source page and bundled extension code load.

## Verify it

```bash
npm run build
npm run check
npm run test:e2e
```

Or run the complete release gate:

```bash
npm run verify
```

The end-to-end test launches the locally installed Google Chrome in a temporary profile.
It exercises capture, navigation removal, exact overlay placement, ambiguity refusal,
cross-inline CJK/RTL/emoji highlighting, paint/unpaint text invariants, persistence,
keyboard access, library search, deletion, whole-library backup, and validated restore.

## Back up and recover

Open **Library → Backup** to download one versioned JSON file containing every frozen
document, highlight anchor, note, and tag. **Library → Restore** validates the entire
file before making a single transactional write; it merges with the current library and
replaces only records carrying the same Marginal ids.

`marginal.html` is retained as the original single-file M3 prototype. The MV3 source of
truth lives under `src/`, and the loadable extension is generated in `dist/`.
