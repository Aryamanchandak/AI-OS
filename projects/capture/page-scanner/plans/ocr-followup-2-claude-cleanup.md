# OCR Follow-up #2 — Optional Claude text-cleanup pass

> ✅ **STATUS: IMPLEMENTED 2026-07-05.** `core/cleanup.py` + `--clean` on
> `process.py`/`ingest.py` (off by default). **One deviation from the plan below:**
> the LLM call is routed through the shared **LLM gateway** in `AI Code/`
> (`http://localhost:8107`, stdlib `urllib` — no `anthropic` SDK, no new dep, no
> per-project API key) instead of the raw Message Batches API. Consequences:
> - Provider is `HG_CLEANUP_PROVIDER` (default `anthropic-haiku` → `claude-haiku-4-5`).
> - **Gateway must be running AND have that provider configured.** Today
>   `AI Code/.env` has only `OPENAI_API_KEY`, so `anthropic-haiku` is *unknown* to
>   the gateway → `--clean` degrades gracefully to raw OCR and logs a loud,
>   actionable warning. To make "text to Claude" live: add `ANTHROPIC_API_KEY` to
>   `AI Code/.env` and start the gateway (`cd AI Code/llm_gateway && .venv/bin/python
>   main.py`). Or `export HG_CLEANUP_PROVIDER=openai-cheap` to use what's configured now.
> - No Batch API (the gateway is single-call); cleanup loops one HTTP call per
>   passage. Cost is still negligible.
> Verified live 2026-07-05: `systern→system`, `l cannot rnake→I cannot make`, clean
> quote returned byte-for-byte; diff-guard + graceful-degrade both fire against the
> real gateway. Tests: `tests/test_cleanup.py` (offline safety proofs). Value-add
> eval: `golden/eval_cleanup.py` (separate from the deterministic `golden/check.py`).
>
> ---
>
> Pick-up plan. Self-contained. Goal: after OCR, run each highlighted passage
> through a **text-only** Claude call that fixes obvious OCR garbles (l↔1, rn↔m,
> broken hyphenation) and pre-fills the cockpit's editable field — WITHOUT ever
> rewording the verbatim quote. Cheap, headless, toggleable, review-gated.
>
> Do Follow-up #1 (`plans/ocr-followup-1-accurate-line-text.md`) FIRST — it's
> free and offline. This pass polishes whatever residue remains.

## Orientation (read first — the pipeline in 90 seconds)

"Highlight Grabber": photograph highlighted book pages → OCR the yellow
highlights → review in a web cockpit → export clean markdown to a Raw Data lake.

- **Stack:** Python 3.11, venv at `.venv/`. `ocrmac` (Apple Vision OCR), opencv,
  pillow, pillow-heif, numpy, FastAPI. SQLite at `data/processed.db`.
- **Core rule (load-bearing here):** OCR text only becomes durable after a human
  **accepts** the page in the cockpit. `edited_text` is the human-owned field;
  `ocr_text` is the raw recognizer output. The DB is disposable; typed edits are not.
- **Flow:** `ingest.py` → `process.process_image()` → rows in `processed.db` →
  cockpit (`server.py`) edits `edited_text` → on accept, `core/publish.py` writes
  markdown into the Raw Data lake.

This cleanup pass sits in the **processor**, between grouping and storage. It only
changes what text pre-fills `edited_text`. **The human review gate is the backstop**
that makes this safe.

## Why this is allowed (not the parked VLM work)

The project's parked list includes "VLM / Ollama integration." This is **not**
that: the model never sees the image. It receives OCR *text* and returns
*corrected text*. Different capability, different risk profile.

## Key code touchpoints

- `process.py:145` `process_image()` — where passages get their text. After
  grouping, each passage's text is built (`_passage_text` / the #1 accurate
  variant) and passed to `store.insert_passage(...)`.
- `core/store.py::insert_passage(db, page_id, *, bbox, ocr_text, edited_text=None,
  ...)` — `edited_text` defaults to `ocr_text`. **The cleanup output should go into
  `edited_text`; the raw OCR stays in `ocr_text`.** Nothing is lost.
- `core/store.py::insert_passage` also stores `min_conf` — usable to run cleanup
  **only on low-confidence passages** to cut cost/blast-radius.
- The cockpit (`static/review.js`, `server.py::api_save`) already edits and
  persists `edited_text`. No cockpit change needed — cleanup just gives the human
  a better starting draft.

## Model + cost (grounded against the claude-api reference)

- **Model:** `claude-haiku-4-5` — the right tier for constrained correction.
  Pricing: **$1 / 1M input, $5 / 1M output**, 200K context. (You do NOT need
  Opus/Sonnet to fix `rn`→`m`.)
- **Per passage:** ~300 input tokens (passage + instructions) + ~80 output ≈
  **~$0.0007**. A ~200-highlight book ≈ **~14¢**.
- **Halve it with the Batch API:** the processor is headless / not latency-
  sensitive — the ideal batch shape. Batch = 50% off → **~7¢/book**. Results are
  unordered; key by a `custom_id` you control (e.g. `passage_id`).
- **SDK:** official `anthropic` Python SDK (`pip install anthropic`), NOT raw
  HTTP. Default model string `claude-haiku-4-5`. Auth: `ANTHROPIC_API_KEY` env
  var, or an `ant auth login` profile (a bare `Anthropic()` client picks it up).
  Confirm a key/profile exists before building — ask the user; do not hardcode.

## Design

1. **New module** `core/cleanup.py` with `clean_passages(passages: list[str],
   *, batch: bool = True) -> list[str]`. Input = raw OCR strings; output = same
   length, each either corrected or **unchanged** (never dropped/reordered).
2. **System prompt (conservative — this is the whole safety story):**
   - "You correct OCR errors in verbatim book highlights."
   - "Fix ONLY clear optical mistakes: l↔1, O↔0, rn↔m, broken hyphenation across
     line breaks, stray artifacts."
   - "NEVER reword, paraphrase, add, remove, reorder, or 'improve' text. Preserve
     original punctuation, casing, and British/American spelling."
   - "If you are not confident a change is an OCR error, return the text UNCHANGED."
   - Return only the corrected text, no commentary. (Use structured output /
     one-passage-per-call or a strict per-item batch so outputs map 1:1 to inputs.)
3. **Diff-guard (mandatory).** After the model returns, compute normalized edit
   distance between input and output. If it exceeds a threshold (start **15%** of
   length), **reject** the correction, keep the raw OCR, and flag the passage
   (e.g. a `color_tag`/note) so a large "correction" can never slip in silently.
4. **Placement in `process_image`:** after grouping, collect the page's passage
   texts, call `clean_passages`, and pass each result as `edited_text` to
   `insert_passage` while keeping the raw string as `ocr_text`.
5. **Toggle:** off by default. Add `--clean` to `process.py` / `ingest.py`
   argparse (thread through `args.clean`, like `args.hsv`/`args.book_meta` are
   threaded today). No flag → behavior identical to now.
6. **Optional cost cut:** only clean passages with `min_conf <= LOW_CONF`
   (`LOW_CONF = 0.5` already defined in `process.py`). High-confidence passages
   skip the call.

## Implementation steps

1. `pip install anthropic` into `.venv`; confirm `ANTHROPIC_API_KEY` (or `ant`
   profile) is available. If not, stop and ask the user.
2. Write `core/cleanup.py` (`clean_passages`, the system prompt, the diff-guard,
   a `_normalized_edit_distance` helper — `golden/check.py` already has a
   `levenshtein` you can copy).
3. For batch mode, use the Message Batches API (`client.messages.batches.*`),
   `custom_id = str(passage_id)` or an index; reassemble by `custom_id` (results
   are unordered).
4. Thread a `--clean` flag through `process.py` and `ingest.py`; in
   `process_image`, branch: if `args.clean`, run `clean_passages` and store the
   result as `edited_text` (raw stays `ocr_text`); else current behavior.
5. Log per-page: how many passages were cleaned, how many corrections the
   diff-guard rejected.

## Testing / acceptance

- **Unit:** feed known garbles ("systerns" → "systems", "l've" → "I've") and
  confirm they're fixed; feed a clean quote and confirm it's returned byte-for-byte;
  feed a passage where the model tries a large rewrite (or simulate one) and
  confirm the diff-guard rejects it and keeps raw OCR.
- **Golden:** `.venv/bin/python golden/check.py` should **improve or hold** with
  `--clean`; must be **identical to baseline without** `--clean` (proves the flag
  is truly off by default).
- **End-to-end:** run `ingest.py --clean` on a test book (isolate with a temp
  `PS_SOURCE_DIR` / `HG_DB` — see how `core/publish.py` tests do it), open the
  cockpit, confirm `edited_text` is pre-filled cleaner and raw `ocr_text` is intact.
- **Cost check:** log token usage; confirm ~sub-cent per passage.

## Risks

- **The one real risk:** an LLM can silently alter a verbatim quote. Contained by
  (a) the conservative prompt, (b) the diff-guard rejecting large edits, (c) raw
  OCR preserved in `ocr_text`, and (d) the human review gate — every page is still
  eyeballed before it becomes durable. Ship all four.
- **Off-by-default** means zero risk unless explicitly enabled.
- Network dependency + API key: acceptable because it's opt-in and batched.

## Cost / risk / effort

- **Cost:** ~7–14¢/book + an API key. Effectively negligible.
- **Risk:** low WITH the guardrails; non-zero (only option that can introduce a
  wrong-but-plausible word). Review gate is the backstop.
- **Effort:** ~half a day incl. diff-guard + toggle + batch wiring.

## Definition of done

- `core/cleanup.py` exists with the conservative prompt + diff-guard.
- `--clean` flag on `process.py` and `ingest.py`, **off by default**; off-path is
  byte-identical to current behavior.
- Raw OCR preserved in `ocr_text`; cleaned text only ever pre-fills `edited_text`.
- Tests above passing; golden holds/improves with the flag, unchanged without it.
- One-line note added to project memory that #2 is done, referencing
  [[rawdata-wiring]] and this plan.
