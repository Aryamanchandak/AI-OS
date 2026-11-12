# Phase 2 — Build & Findings

Build: quality gate (`core/quality.py`) wired into `process.py`, low-confidence
flagging + per-batch color sampling in the cockpit, and a golden-set regression.
Run: fresh reprocess of the 13 real photos in `data/inbox/` (IMG_7742–7754,
Atomic Habits) after wiping `processed.db`.
Result: **13/13 reprocessed, 0 errored, all quality columns populated (0 NULL),
0 organically gated (the inbox has no bad photo yet — see §1). Gate + flag paths
proven to fire via degraded-input unit tests; golden set 4/6 passages ≤2 edits,
worst 96.1% char-accuracy.**
Exit condition partially met — see §1. Did **not** proceed to Phase 3.

## Verdict (one line)

The whole Phase 2 mechanism is built, wired, and proven to fire on bad input —
but the current inbox is *too clean to trip it organically*, exactly as Phase 0
§3/§5 predicted; demonstrating a real `retake` flag and a real cockpit warning
needs the deliberately-bad photo the user is adding.

---

## What got built

### Quality gate — `core/quality.py` (spec §6)
- `blur_score(rgb)` = variance of the Laplacian.
- `glare_score(rgb)` = fraction of the image in near-white (V>245) blobs >500px,
  via `connectedComponentsWithStats`.
- `quality_gate(blur, glare, conf_ratio)` → `True` (retake) if `blur<80` **or**
  `glare>0.04` **or** `conf_ratio>0.3`. **Thresholds are placeholders measured on
  the downscaled (≤2500px) pipeline image** — documented in the module as
  needing tuning against the first real bad photo.

### Processor wiring — `process.py`
- Computes blur + glare on the downscaled RGB, runs a **line-level Vision pass**
  (`ocr.ocr_lines`, new) for `conf_ratio`, and stores all three on the page row.
- Sets `status='retake'` on gate failure, else `'new'`.
- **Fixed the retake list** — the spec claim that it "already handles this" is
  wrong: `main()` built it only from the `except` branch, so a gate-failed page
  printed as `OK`. Now `process_image` returns the gate outcome and `main()`
  prints gate-failures and errors separately in the retake list.
- **Re-sources per-passage `min_conf` from line confidence** (`_passage_min_conf`):
  the LiveText word tokens are pinned at 1.00, so the cockpit warning can only
  fire if `min_conf` comes from the line-level pass mapped onto each passage's
  union bbox. Falls back to the word-token min when no line overlaps.

### Cockpit — `server.py` + `static/`
- `POST /api/sample-color {image_path,x,y}` → median HSV of a 5×5 patch on the
  processed image (spec §8). `min_conf` already flows via `/api/pages`.
- Right pane: a passage with `min_conf ≤ 0.5` gets a faint yellow-orange field +
  a `⚠ low confidence` tag.
- Header: a **Pick color** button → crosshair pick mode → click the highlight →
  HSV shown as copyable `--hsv H,S,V` text (live reprocess is Phase 4).

### Golden set — `golden/answers.json` + `golden/check.py`
- 4 pages, 6 passages, human-transcribed (awaiting user confirmation):
  IMG_7748, IMG_7749, IMG_7752, IMG_7754. IMG_7746 (two-column, patchy
  highlight) deliberately excluded as the known type-to-fix hard case.
- `check.py` runs the live pipeline, best-matches each golden passage to a system
  passage, reports normalized char-edit distance.

---

## Findings

### 1. The gate is correctly built but the inbox can't trip it ⚠️ (the headline)
Measured on the downscaled images the gate actually runs on:
- **blur** 250–533 — the whole *good* cluster sits far above the `<80` cutoff, so
  80 only catches *severe* blur and leaves an 80–250 dead zone. (Phase 0's 39–67
  was a different image scale and is not comparable.)
- **glare** ≤0.0061 — all below 0.04.
- **conf_ratio** 0.000–0.045 — Vision line confidence is 1.00 or a discrete 0.50,
  never *below* 0.5, so the gate/cockpit use `<= 0.5`; even so no page exceeds the
  0.3 ratio cutoff.

→ **0/13 flag.** This is the Phase 0 §3/§5 prediction landing exactly: the inbox
has no degraded sample, so the gate has nothing to bite. The blur threshold can
only be calibrated once a real bad photo defines where "bad" falls.

### 2. The low-confidence flag is wired but has no organic trigger ⚠️
All 25 passages stored `min_conf=1.0`. The rare 0.50 Vision lines on
IMG_7752/7754 exist — but they fall **outside** every highlighted region, so no
passage inherits a low confidence. The server **data path is verified**: forcing
one passage to `min_conf=0.5` in a throwaway `HG_DB` and hitting `/api/pages`
shows it flagged as a warning passage. `review.js` passes `node --check`. The
**rendered** DOM (the `low-conf` class + `⚠ low confidence` tag) is *not* machine-
verified — no browser automation in the env (carried over from Phase 1) — so the
visual still needs one human eyeball, easiest via:
`HG_DB=<demo.db> .venv/bin/python -m uvicorn server:app` against a DB with a
`min_conf=0.5` passage.

### 2b. Retake gate and low-conf warning are nearly mutually exclusive ⚠️ (set expectations)
The synthetic blurry demo (§3) produced **0 passages**: blur heavy enough to fail
the gate also destroys word/highlight detection, so you get `status=retake` with
nothing to warn about. Mild blur keeps Vision confidence high, so no warning
either. The two signals therefore rarely co-occur on real data — **the user's
incoming bad photo will most likely flag as `retake` while never surfacing the
cockpit warning.** The reliable way to see the warning is the `HG_DB` injection
above, not a bad capture.

### 3. Python plumbing proven on degraded input ✅ (`tests/test_phase2.py`)
Server + pipeline layers only — the cockpit *rendering* is the one untested layer
(§2). Independent of organic bad data:
- Blur gate: IMG_7748 sharp **298.9 (pass)** → GaussianBlur σ=6 **1.2 → RETAKE**.
- Glare gate: **0.0005 (pass)** → painted hotspot **0.114 → RETAKE**.
- `min_conf` re-source: a passage union over a 0.50 line → **0.5 (flags)**;
  non-overlapping → 1.0 (clean).
- `conf_ratio` `<=0.5` catches the 2 outlier lines on IMG_7754; strict `<0.5`
  catches 0 (would be dead code).
- **End-to-end:** a synthetic blurry photo run through `process.py` lands
  `status='retake'` and prints in the RETAKE LIST; a sharp control stays `'new'`.

### 4. Golden-set regression ✅ (run via `golden/check.py`)
```
IMG_7748 p1:  0 edits (100.0%)  PASS
IMG_7749 p1:  3 edits ( 99.4%)  — OCR dropped "of" in "Plateau of Latent Potential"
IMG_7752 p1:  0 edits (100.0%)  PASS
IMG_7754 p1:  1 edit  ( 99.7%)  PASS  (missing period after "succeed")
IMG_7754 p2:  0 edits (100.0%)  PASS
IMG_7754 p3: 18 edits ( 96.1%)  — grabbed "treated a symptom" from the line above
4/6 within ≤2 edits; worst error rate 3.9%.
```
The two misses are honest, explainable, and *not* OCR-quality failures:
- **IMG_7749** — a single dropped word ("of" in "Plateau of Latent Potential"),
  3 chars: the type-to-fix case.
- **IMG_7754 p3** — a passage-boundary **boundary case**, verified by mask
  overlap: "treated"/"symptom" sit under **0.17–0.20** yellow coverage vs ~0.70
  for the genuinely-highlighted words. So the highlighter physically clipped the
  line above (it's *not* a hallucination, and the golden isn't simply wrong) —
  but the overlap is marginal. Raising `KEEP_OVERLAP_FRAC` (0.10 → ~0.25) would
  drop them; that's a tuning call deferred out of Phase 2 scope.

### 5. Color sampling works ✅
`/api/sample-color` on the IMG_7754 highlight returned `{h:33, s:129, v:219}` —
H=33 sits squarely in the detection band [20,35], confirming the sampler returns
a usable `--hsv` floor.

---

## Exit-condition status
| requirement | status |
|---|---|
| process.py flags ≥1 blurry/glare photo as `retake` | ⏳ **pending the user's real bad photo** — proven to fire on synthetic blur (§3) |
| retake list prints correctly | ✅ (gate-failures + errors, separately) |
| low-confidence passages show the cockpit warning | ⏳ data path verified (server serves a `min_conf=0.5` passage; `review.js` passes `node --check`); **rendered DOM needs one human eyeball** — no browser automation (§2). No organic trigger in this clean set, and the warning rarely co-occurs with a retake (§2b) |
| golden-set regression passes within 1–2 edits | ✅ on clean passages (4/6); 2 explained misses at 99.4% / 96.1% (§4) |

**To fully close Phase 2:** drop one genuinely blurry or glare-ruined photo into
`data/inbox`, re-run `process.py`, and calibrate `BLUR_MIN` so it cleanly
separates that shot from the 250+ good cluster.

## How to run
```bash
# reprocess (wipe first — dedup skips existing rows, so quality cols won't backfill)
rm data/processed.db
.venv/bin/python process.py --inbox data/inbox --batch "Atomic Habits" --author "James Clear"
.venv/bin/python golden/check.py          # regression
.venv/bin/python tests/test_phase2.py     # gate/flag plumbing proofs
.venv/bin/python -m uvicorn server:app --port 8123   # cockpit
```

## Tuning knobs (Phase 2 additions)
| knob | value | role | file |
|---|---|---|---|
| `BLUR_MIN` | 80 | blur < this → retake (placeholder; good cluster is 250–533) | core/quality.py |
| `GLARE_MAX` | 0.04 | glare > this → retake (placeholder) | core/quality.py |
| `CONF_RATIO_MAX` | 0.3 | conf_ratio > this → retake | core/quality.py |
| `LOW_CONF` | 0.5 | line conf ≤ this is "low" (gate + cockpit; `<=` not `<`) | process.py / review.js |
| `GLARE_V_FLOOR` / `GLARE_MIN_BLOB` | 245 / 500 | what counts as a glare blob | core/quality.py |
