# Marginal — build plan

A single-user highlighting tool for web articles, in the spirit of Readwise Reader.

Status: **M7 complete** (unpacked extension builds to `dist/`; `marginal.html` remains
the original M3 prototype). This document is the plan and the record of which decisions
are already locked.

Revision 2 — supersedes the original plan. Section 2 lists what changed and why.

---

## 1. Scope

**Building:** a Chromium extension that freezes web articles into a local library,
and a reading surface where highlighting them is fast, precise, and permanent.

**One user. One highlight colour. Web articles only.**

Success condition, stated as a feeling rather than a feature: *you highlight without
thinking about whether the highlight will still be there.* Everything below serves that.

### Explicitly not building (and the trigger that would change my mind)

| Deferred | Un-defer when |
|---|---|
| Accounts, cloud sync | A second device you actually read on |
| PDF and EPUB annotation | You've read 20 articles here without reaching for Reader |
| YouTube transcripts | Same |
| Multiple colours | You can name the three categories, and tags have failed at them |
| AI actions | Never, for v1. It hides whether the core is good |
| Sharing, collaboration | It's a single-user tool. This is a different product |
| Native mobile | After capture and reading are boring and stable |

The deferral list is the most valuable part of the original plan and I've kept it
almost intact. The one item I moved *out* of "delay": nothing. The one I'd add: **RSS
and newsletter ingestion is not a v2 either** — it turns a reading tool into a queue
manager, which is a different problem with a different failure mode.

---

## 2. What changed from revision 1

The original plan's core insight — freeze the document — is right and unchanged.
Five corrections:

**2.1 — Dropped the local HTTP service.**
Rev 1 proposed a Chromium extension, a separate reader app, and a loopback API with a
token between them. That's three deployable pieces and an auth scheme for one user.
Now: the reader ships *inside* the extension as a page, and both halves talk to the same
IndexedDB. One artifact, no ports, no daemon, no "is it running" failure mode.
Cost: capture and reading must share an origin. That's acceptable and always was.

**2.2 — Canonical text is now a first-class decision, not a test-suite item.**
Rev 1 listed NBSP, CJK, emoji and whitespace under "testing needed." They aren't test
cases; they're a data-model question, and answering it once deletes most of them.
See §5. This is the single biggest change.

**2.3 — Merge moved to the data layer.**
Rev 1 treated merging as a UI affordance. It is now an invariant of the store:
overlapping or touching highlight records cannot exist. Nested wrapper elements are the
classic silent annotation bug, and this makes them unrepresentable rather than handled.

**2.4 — The reattachment ladder is built but demoted.**
On a frozen document the revision hash always matches and step 1 always wins, so steps
3–5 are unexercised code that will rot. They earn their keep only for live-page overlay,
which is deferred to M6. Mitigation: a **forced re-anchor** command that discards stored
offsets and drives every highlight through search and fuzzy matching, reporting what
landed and what was refused. Untestable code becomes testable on demand. Already built.

**2.5 — Resize is scheduled as a whole milestone, not a bullet.**
Rev 1 listed resize handles alongside "notes" and "undo." Readwise themselves describe
resize as surprisingly hard, and rev 1 quoted that without drawing the conclusion.
Selection boundaries across inline elements are where the time goes.

---

## 3. The load-bearing decisions

Everything else is implementation detail. These four are the design.

**D1. The document is frozen at capture.**
Stored HTML is never re-derived, re-parsed, or refreshed. If the publisher rewrites the
page, your copy is unaffected. This converts "keep an annotation attached to an arbitrary
webpage forever" into "keep an annotation attached to a versioned document I control."

**D2. The record is the highlight; the yellow is a projection.**
The database row is authoritative. DOM wrappers are rebuilt from scratch on every change
and are never read from. Any question of the form "what does the DOM say about this
highlight" is a bug.

**D3. Four anchors, not one.**
Block + offset, global character range, exact quote, and surrounding context. Failure of
one path does not lose the record.

**D4. Refusal beats a wrong guess.**
If reattachment is not both confident *and* clearly better than the runner-up, the
highlight becomes unplaced and lives in the Notebook. A missing overlay is recoverable.
A confidently wrong overlay silently corrupts your notes and destroys trust in the tool.

---

## 4. Architecture

```
┌─ content script ───────────┐
│ Readability on the LIVE dom│  capture is the only thing that
│ serialize → sanitize       │  ever touches a real webpage
└──────────┬─────────────────┘
           │ chrome.runtime message
┌──────────▼─────────────────┐
│ background / service worker│
│ writes doc record          │
└──────────┬─────────────────┘
           │
      ┌────▼──────┐        ┌──────────────────────────────┐
      │ IndexedDB │◄──────►│ reader page (extension page) │
      │ docs      │        │ render → normalise → index   │
      │ highlights│        │ paint → re-index             │
      │ outbox    │        │ notebook, export             │
      └───────────┘        └──────────────────────────────┘
```

Three stores, no server, no network after capture.

**Why Readability runs in the content script, not on the saved HTML:** it needs the
*rendered* DOM. Paywalled and JS-heavy pages return nothing useful to a server fetch.
This is the one genuine reason the extension has to exist.

---

## 5. Data model

### 5.1 Canonical text — the spec that prevents eight classes of bug

Every offset in the system refers to one string, derived deterministically from the
frozen HTML:

1. Insert `doc.html` into the DOM.
2. Walk every text node. In place: replace `U+00A0` with a space, apply `NFC`.
3. Skip any text node inside injected UI (`.glyph`, `.marginnote`, `.grip`).
4. Concatenate leaf-block text, joining blocks with a single `\n`.

Rules that follow, and must not be broken:

- **Normalisation happens once, in the DOM itself.** The canonical string and the live
  text nodes can therefore never drift. Normalising the string separately from the nodes
  is how offset bugs are born.
- **No whitespace collapsing.** Collapsing breaks the 1:1 mapping between the string and
  text-node offsets. Whitespace at selection edges is trimmed at highlight-creation time
  instead, which is where the user actually meant it.
- **Offsets are UTF-16 code units**, consistent with DOM ranges. Emoji and CJK are then
  correct by construction — the failure mode was only ever mixing units.
- Block ids are assigned by document order over a fixed selector. Because the HTML is
  frozen, they are stable across sessions without being stored.

### 5.2 Records

```js
document = {
  id, title, url, capturedAt,
  html,            // sanitised, frozen, never rewritten
  revisionHash     // hash(html) — cheap staleness check
}

highlight = {
  id, docId,
  revisionHash,                              // which revision the anchors describe
  quote:    { exact, prefix, suffix },       // W3C TextQuoteSelector, 40 chars context
  position: { start, end },                  // W3C TextPositionSelector, canonical text
  range:    { startBlockId, startOffset,
              endBlockId,   endOffset },     // structural
  note, tags[],
  createdAt, updatedAt,
  status,          // 'attached' | 'unplaced'
  strategy,        // which ladder rung resolved it — keep it, it's your only telemetry
  confidence
}
```

`strategy` and `confidence` are stored deliberately. They cost nothing and they are the
only way to notice anchoring quietly degrading.

### 5.3 Store invariant

No two attached highlights on a document may overlap or sit within one whitespace
character of each other. Writes that would violate this merge instead: union the range,
concatenate notes, union tags, keep the older id and `createdAt`.

---

## 6. Capture pipeline

1. Clone the rendered DOM.
2. Run Readability for article body + metadata.
3. Sanitize against a tag/attribute allowlist. Readability's own docs warn its output is
   not safe; treat capture as untrusted input, because it is.
4. Preserve: headings, paragraphs, lists, blockquotes, emphasis, links, inline code,
   code blocks, tables, images, figcaptions.
5. Drop: scripts, styles, iframes, embeds, event attributes, `javascript:` and `data:`
   URLs.
6. Hash and store.

**Failure policy:** if Readability returns a body under ~400 characters, do not save a
broken article silently. Offer the raw selection or the full body and say what happened.
Bad captures that look fine are worse than obvious failures.

**Known limit, accepted:** parser quality can't be perfect across arbitrary HTML. The
escape hatch is "open original," plus manual paste. Both already exist.

---

## 7. Reattachment

Runs on load when `highlight.revisionHash !== doc.revisionHash`, and on demand via the
forced re-anchor command.

```
1. Revision matches and text at stored offsets equals the quote  → confidence 1.00
2. Block id + local offset, verified against the quote           → 0.97
3. Global offsets, verified against the quote                    → 0.95
4. Search every exact occurrence of the quote.
   Score each by prefix suffix overlap and drift from the old position.
   Accept only if unique, or if best beats runner-up by ≥ 0.05   → ~0.55–0.99
5. Fuzzy: bigram Dice over sliding windows of quote length.
   Accept only if ≥ 0.82 and beats runner-up by ≥ 0.04           → ~0.82–0.99
6. Otherwise: status = 'unplaced'. Keep the record. Show it in the Notebook.
```

Every accepting rung **verifies against the stored quote**. A rung that returns a
position without checking the text is not a fallback, it's a corruption path.

The margin requirements in steps 4 and 5 are what implement D4. Repeated identical
sentences are the case they exist for: four equally-good candidates means *refuse*, not
*pick the first*.

---

## 8. Rendering contract

```
render(doc.html)       // original text, always — wipes every wrapper
normalise(textNodes)   // NBSP, NFC, once
index()                // text node ↔ global offset map
paint(highlights)      // reverse document order, reverse parts within a node
index()                // again, over the painted tree
```

Rebuilding wholesale is not a performance problem at article scale, and it buys the
invariant: **removing every wrapper always restores exactly the captured text.**

Painting runs in reverse order because `surroundContents` splits the text node it
operates on, leaving the leading fragment under the original reference. Reverse order
keeps earlier offsets valid without re-indexing between wraps.

One logical highlight may produce several visual fragments (across links, emphasis,
list items). All fragments share one `data-highlight-id`; interactions bind to the id,
never to a fragment.

---

## 9. Interaction grammar

The same verbs everywhere, because consistency is the feature.

| Gesture | Result |
|---|---|
| Select text | Highlight, immediately, no confirmation |
| `Alt` + select | Select without highlighting |
| `↓` `↑` | Move paragraph focus |
| `H` | Highlight the focused paragraph |
| `N` | Highlight and open a note |
| `T` | Tag the active highlight |
| `Z` | Undo, multi-step |
| Drag either grip | Resize the boundary |
| `Esc` | Dismiss |

Two ordering rules:

- **Capture first, enrich later.** Notes, tags, copy and delete are offered *after* the
  passage is already saved. Never a form before the thought is kept.
- **Errors are cheap.** Undo, resize, merge, and delete are all one action, so the first
  gesture doesn't have to be precise. This is what makes fast highlighting feel safe.

One colour, with tags for meaning. Colour-picking turns every highlight into a
classification decision, which is exactly the deliberation this design removes.

---

## 10. Storage and sync

IndexedDB. Documents, highlights, preferences. Highlights write on every mutation;
the paint happens first and never waits on the write.

Sync is out of scope, but the shape is reserved: an `outbox` table of mutations with
ids and timestamps. Local-first means the reading gesture never blocks on a network.
If sync ever arrives, nothing above changes.

Export is the real durability story: Markdown and JSON, on demand, containing the exact
captured quote and its source. If this project is abandoned, the notes survive it.

---

## 11. Milestones

| | Milestone | Exit criteria | Status |
|---|---|---|---|
| M0 | Frozen document + canonical text | A pasted article renders; offsets are stable across reloads | done |
| M1 | Highlight create, paint, persist | Select → yellow → reload → still there | done |
| M2 | Notes, tags, undo, merge, Notebook, export | Full loop usable on one document | done |
| M3 | Resize | Both grips, across inline elements, across blocks, no text mutation | done |
| M4 | Extension capture | Readability + sanitize + save from any article page | done |
| M5 | Library | Many documents, search over quotes, delete, re-open original | done |
| M6 | Live-page overlay | Highlights made in Reader shown on the original site, or refused | done |
| M7 | Trust + release readiness | Backup/restore, durable writes, accessibility, hostile-corpus regression gate | done |

M3 before M4 deliberately: resize is where the selection model breaks, and it's better
to break it on three hand-picked documents than on the open web.

M6 is the only milestone where the fuzzy ladder actually earns its cost. If M6 never
happens, steps 4–5 remain a safety net for your own renderer changes — which is a real
risk, not a hypothetical one.

Implementation note (July 2026): M4–M6 ship as a Chromium Manifest V3 extension.
Readability and DOMPurify are bundled into the action-injected capture script. The
reader, service worker, and overlay share one extension-origin IndexedDB. The live-page
overlay accepts a unique exact/context match or a clearly superior fuzzy match; all
other cases are reported as refused and left untouched.

M7 makes that finished feature set recoverable and testable rather than expanding it.
The reader now exports and validates a versioned whole-library backup, storage writes
that span related records are transactional, rapid highlight saves are serialized, and
storage startup failures are shown instead of masquerading as an empty library. The
reader and injected page UI expose keyboard focus, dialog semantics, live status, and
reduced-motion behavior. `tests/fixtures/hostile-article.html` is the permanent browser
corpus, and `npm run verify` is the release gate.

---

## 12. Test corpus and invariants

Keep a permanent folder of hostile documents. Add to it every time something breaks;
never delete from it.

Must include: nested emphasis and links; lists spanning items; inline code and code
blocks; tables; **repeated identical sentences**; emoji and multi-code-point characters;
Chinese, Arabic, right-to-left text; non-breaking spaces and irregular whitespace;
quotes at screen edges; very long paragraphs; images wrapped in links; a document edited
between visits.

The invariants, checked against all of them:

1. Highlighting never changes the visible text.
2. Removing the wrappers restores the captured DOM text exactly.
3. Reload returns every highlight to the same passage.
4. Resize moves only the dragged boundary.
5. A low-confidence resolution becomes unplaced — never a guess.
6. Creating a highlight never moves the reading position.
7. Highlights created offline survive a restart.
8. Export contains the exact captured quote and its source.
9. Special characters round-trip without normalisation damage.

Invariant 2 is the one to automate first. It catches more than the other eight combined,
and it's three lines: render, paint, unpaint, compare to `doc.html`'s text.

---

## 13. Risks

| Risk | Likelihood | Response |
|---|---|---|
| Selection boundaries across inline elements | High | M3 is scheduled for exactly this |
| Fuzzy path rots from disuse | High | Forced re-anchor command, run against the corpus |
| Readability fails on a site you care about | Medium | Manual paste path already exists; never fail silently |
| Repaint cost on very long documents | Low | Article scale is fine. If books arrive, paint per viewport |
| Scope creep into a read-later queue | Medium | §1's deferral table is the answer. Re-read it before adding anything |

The honest overall risk: a proof of concept is small; a version you *trust* is not. The
difficulty lives in anchoring, selection boundaries, rich text, resize, and a few hundred
edge cases. For one user and web articles only, that's a finite amount of work — but it
is the work, and the yellow rectangle was never the hard part.

---

## 14. Stack

- TypeScript throughout — the anchoring code is exactly where types pay for themselves.
- Chromium Manifest V3.
- Preact for the reader UI. React is fine; the point is no framework in the paint path.
- Mozilla Readability for extraction.
- An allowlist sanitizer. DOMPurify if you want the battle-tested one; ~60 lines if not.
- IndexedDB, via idb or raw.
- ULIDs for document, block and highlight ids — sortable, and useful if sync ever lands.
- Markdown and JSON export as the permanent escape hatch.

No server. No ports. No tokens.
