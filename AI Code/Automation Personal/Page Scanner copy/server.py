"""Stage 2 — review cockpit server (FastAPI).

Serves the static cockpit and a tiny read/save API over the precomputed DB.
Never runs OCR: everything it shows is already in processed.db.

  .venv/bin/python -m uvicorn server:app --reload
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import export, images, ocr, settings, store

os.environ.setdefault("RAW_DATA_ROOT", str(settings.RAW_DATA_ROOT))
# Review/spellcheck/image-gate backends moved to the ingestion-pipeline repo
# (2026-07-18 code/data separation): Database/Raw Data/lib -> ingestion-pipeline/src/pipeline/core
_PIPELINE_SRC = str(Path(settings.RAW_DATA_ROOT).parent.parent / "ingestion-pipeline" / "src")
if _PIPELINE_SRC not in sys.path:
    sys.path.insert(0, _PIPELINE_SRC)

try:
    from pipeline.core import images as raw_images  # noqa: E402
    from pipeline.core import review as raw_review  # noqa: E402
    from pipeline.core import spellcheck as raw_spellcheck  # noqa: E402
    _REVIEW_ERR = None
except Exception as e:
    raw_images = None
    raw_review = None
    raw_spellcheck = None
    _REVIEW_ERR = e

try:
    from core import publish            # Raw Data lake wiring (optional at runtime)
    _PUBLISH_ERR = None
except Exception as e:                  # lake unreachable / lib import failed
    publish = None
    _PUBLISH_ERR = e

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DB = os.environ.get("HG_DB", str(ROOT / "data" / "processed.db"))
OUTPUT_DIR = ROOT / "data" / "output"

app = FastAPI(title="Highlight Grabber — cockpit")


class PassageEdit(BaseModel):
    id: int
    edited_text: str


class SavePayload(BaseModel):
    passages: list[PassageEdit] = []
    page_number: int | None = None
    author: str | None = None
    status: str


class OcrBoxPayload(BaseModel):
    page_id: int
    bbox: list[int]   # [x, y, w, h] in natural (load_image) pixel coords


class SampleColorPayload(BaseModel):
    image_path: str
    x: int
    y: int


class ProcessingSavePayload(BaseModel):
    content: str


class ImageApprovalPayload(BaseModel):
    index: int
    approved_text: str


class GlossaryApplyPayload(BaseModel):
    shorthand: str
    expansion: str
    confirmed: bool = False


class SpellcheckPayload(BaseModel):
    text: str


@app.get("/")
def index(queue: str = "ocr") -> HTMLResponse:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = _inject_queue_tabs(html, queue)
    if queue == "processing":
        html = html.replace(
            '<script src="/static/review.js"></script>',
            f"<script>{_PROCESSING_QUEUE_JS}</script>",
        )
    return HTMLResponse(html)


def _inject_queue_tabs(html: str, queue: str) -> str:
    queue_css = """
  <style>
    .queue-tabs {
      position: absolute;
      left: 50%;
      bottom: -18px;
      transform: translateX(-50%);
      display: inline-flex;
      gap: 3px;
      padding: 3px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: var(--shadow);
      z-index: 8;
    }
    .queue-tabs a {
      color: var(--ink-2);
      text-decoration: none;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
      padding: 5px 10px;
      border-radius: 6px;
      white-space: nowrap;
    }
    .queue-tabs a.active {
      color: var(--ink);
      background: var(--amber-soft);
      box-shadow: inset 0 0 0 1px var(--amber-line);
    }
    body.processing-queue .author-input,
    body.processing-queue .book-meta,
    body.processing-queue #pick-color,
    body.processing-queue #hsv-readout,
    body.processing-queue #export-csv,
    body.processing-queue .pageno,
    body.processing-queue #page-img,
    body.processing-queue #overlay {
      display: none;
    }
    body.processing-queue .image-pane {
      align-items: stretch;
      justify-content: stretch;
      padding: 22px;
    }
    body.processing-queue .image-wrap {
      width: 100%;
      max-height: none;
      border-radius: 8px;
      overflow: auto;
      background: var(--surface);
    }
    .processing-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 12px;
      line-height: 1.35;
    }
    .processing-row {
      width: 100%;
      text-align: left;
      cursor: pointer;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface-2);
      color: var(--ink);
      padding: 10px 11px;
      transition: border-color 0.16s var(--ease), background 0.16s var(--ease);
    }
    .processing-row:hover,
    .processing-row.active {
      border-color: var(--amber-line);
      background: var(--surface);
    }
    .processing-row strong {
      display: block;
      overflow-wrap: anywhere;
      font-size: 13px;
      margin-bottom: 5px;
    }
    .processing-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      color: var(--muted);
      font-size: 11px;
    }
    .processing-tag {
      border: 1px solid var(--line-2);
      border-radius: 999px;
      padding: 1px 7px;
      background: var(--surface);
    }
    .processing-editor {
      width: 100%;
      flex: 1;
      min-height: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      resize: none;
      color: var(--ink);
      background: var(--surface-2);
      font-family: "Newsreader", Georgia, serif;
      font-size: 18px;
      line-height: 1.55;
    }
    .processing-editor:focus {
      outline: 2px solid var(--amber);
      outline-offset: 2px;
    }
    .processing-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      padding: 12px 26px;
      border-top: 1px solid var(--line);
      background: var(--surface);
    }
    .source-preview {
      width: 100%;
      min-height: 100%;
      display: grid;
      place-items: center;
      padding: 16px;
      background: var(--surface-2);
    }
    .source-preview img {
      max-width: 100%;
      max-height: calc(100vh - var(--topbar-h) - 92px);
      object-fit: contain;
      border-radius: 6px;
      box-shadow: var(--shadow);
      background: #fff;
    }
    .source-missing {
      color: var(--muted);
      font-family: "Newsreader", Georgia, serif;
      font-size: 18px;
      line-height: 1.5;
      padding: 24px;
      text-align: center;
    }
    .image-review-copy {
      color: var(--ink-2);
      font-size: 13px;
      line-height: 1.5;
      margin-bottom: 12px;
    }
    .glossary-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface-2);
      padding: 12px;
      margin-bottom: 14px;
    }
    .glossary-row {
      display: grid;
      grid-template-columns: minmax(90px, 0.8fr) minmax(130px, 1.2fr) auto auto;
      gap: 8px;
      align-items: center;
    }
    .glossary-row input[type="text"] {
      min-width: 0;
      font: inherit;
      font-size: 13px;
      color: var(--ink);
      background: var(--surface);
      border: 1px solid var(--line-2);
      border-radius: 7px;
      padding: 7px 9px;
    }
    .glossary-row input[type="text"]:focus {
      outline: 2px solid var(--amber);
      outline-offset: 1px;
      border-color: transparent;
    }
    .glossary-remember {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--ink-2);
      font-size: 12px;
      white-space: nowrap;
    }
    .glossary-suggestions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }
    .glossary-suggestion {
      border: 1px solid var(--line-2);
      border-radius: 999px;
      background: var(--surface);
      color: var(--ink-2);
      cursor: pointer;
      font: inherit;
      font-size: 12px;
      padding: 4px 8px;
      transition: border-color 0.16s var(--ease), background 0.16s var(--ease);
    }
    .glossary-suggestion:hover {
      border-color: var(--amber-line);
      background: var(--amber-soft);
      color: var(--ink);
    }
    .spell-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      padding: 12px;
      margin-bottom: 14px;
    }
    .spell-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }
    .spell-title {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .spell-list {
      display: flex;
      flex-direction: column;
      gap: 7px;
    }
    .spell-edit {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 8px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--surface-2);
      padding: 8px;
      animation: rise 0.24s var(--ease) both;
    }
    .spell-edit del {
      color: var(--red);
      text-decoration-thickness: 1.5px;
    }
    .spell-edit ins {
      color: var(--green);
      text-decoration: none;
      font-weight: 600;
    }
    .spell-line {
      color: var(--muted);
      font-size: 11px;
      margin-right: 7px;
    }
    .spell-empty {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
  </style>
"""
    tabs = f"""
    <nav class="queue-tabs" aria-label="Review queues">
      <a href="/?queue=ocr" class="{'active' if queue != 'processing' else ''}">OCR</a>
      <a href="/?queue=processing" class="{'active' if queue == 'processing' else ''}">Processing</a>
    </nav>
"""
    html = html.replace("</head>", queue_css + "\n</head>")
    html = html.replace("</header>", tabs + "\n  </header>", 1)
    if queue == "processing":
        html = html.replace("<body>", '<body class="processing-queue">', 1)
    return html


_PROCESSING_QUEUE_JS = r"""
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    batch: $("batch"),
    counter: $("counter"),
    statusPill: $("status-pill"),
    split: $("split"),
    passages: $("passages"),
    imageWrap: $("image-wrap"),
    curtain: $("curtain"),
    curtainInner: $("curtain-inner"),
    toast: $("toast"),
  };

  const state = {
    items: [],
    glossary: [],
    idx: 0,
    current: null,
    editor: null,
    currentImage: null,
    spellingEdits: [],
    mode: "list",
  };

  async function load() {
    setHeader();
    try {
      await refreshItems();
    } catch (err) {
      return showCurtain(`Couldn't load processing queue.<br><small>${err.message}</small>`, true);
    }
    if (!state.items.length) {
      return showCurtain("No processing items waiting.<br><small>Run the sync step to claim feeder files.</small>", false);
    }
    els.split.hidden = false;
    hideCurtain();
    await openItem(0);
  }

  async function refreshItems() {
    const [itemsRes, glossaryRes] = await Promise.all([
      fetch("/api/processing/items"),
      fetch("/api/processing/glossary"),
    ]);
    if (!itemsRes.ok) throw new Error(`HTTP ${itemsRes.status}`);
    if (!glossaryRes.ok) throw new Error(`HTTP ${glossaryRes.status}`);
    const data = await itemsRes.json();
    const glossaryData = await glossaryRes.json();
    state.items = data.items || [];
    state.glossary = glossaryData.glossary || [];
  }

  function setHeader() {
    els.batch.textContent = "Processing queue";
    els.statusPill.textContent = "mutable";
    els.statusPill.dataset.status = "new";
  }

  function renderList() {
    els.imageWrap.innerHTML = "";
    const list = document.createElement("div");
    list.className = "processing-list";
    state.items.forEach((item, index) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "processing-row";
      row.dataset.path = item.path;
      row.innerHTML = `
        <strong>${escapeHtml(item.name)}</strong>
        <span class="processing-meta">
          <span class="processing-tag">${item.route_hint === "image_review" ? "phase 1" : "phase 2"}</span>
          <span class="processing-tag">${item.unresolved_image_count || 0}/${item.image_count || 0} images</span>
          <span class="processing-tag">${item.editable ? "editable" : "binary"}</span>
          ${item.edited_obsidian_note ? '<span class="processing-tag">edited note</span>' : ""}
        </span>
      `;
      row.addEventListener("click", () => openItem(index));
      list.appendChild(row);
    });
    els.imageWrap.appendChild(list);
    markActive();
  }

  async function openItem(index) {
    const summary = state.items[index];
    if (!summary) return;
    state.idx = index;
    els.counter.textContent = `${index + 1} / ${state.items.length}`;
    els.statusPill.textContent = summary.route_hint;

    if ((summary.unresolved_image_count || 0) > 0) {
      state.mode = "image";
      await renderImageGate(summary);
      return;
    }

    state.mode = "text";
    renderList();
    await renderTextEditor(summary);
  }

  async function renderImageGate(summary) {
    els.passages.innerHTML = "";
    els.imageWrap.innerHTML = `<div class="source-missing">Loading source image...</div>`;

    let imageState;
    try {
      const res = await fetch(`/api/processing/images?path=${encodeURIComponent(summary.path)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      imageState = await res.json();
    } catch (err) {
      return toast(`Image review failed: ${err.message}`);
    }

    const image = (imageState.placeholders || []).find((item) => !item.approved);
    if (!image) {
      await refreshItems();
      await openItem(state.idx);
      return;
    }
    state.currentImage = { path: summary.path, index: image.index };

    const source = document.createElement("div");
    source.className = "source-preview";
    if (image.image_path) {
      const img = document.createElement("img");
      img.alt = image.original || `image ${image.index}`;
      img.src = `/api/processing/image?path=${encodeURIComponent(summary.path)}&index=${image.index}`;
      source.appendChild(img);
    } else {
      source.innerHTML = `<div class="source-missing">Image file missing for ${escapeHtml(image.original || image.token)}</div>`;
    }
    els.imageWrap.innerHTML = "";
    els.imageWrap.appendChild(source);

    let candidate = image;
    try {
      const res = await fetch(`/api/processing/image-candidate?path=${encodeURIComponent(summary.path)}&index=${image.index}`);
      if (res.ok) candidate = await res.json();
    } catch (_) {
      candidate = image;
    }

    const card = document.createElement("div");
    card.className = "passage";
    card.innerHTML = `
      <div class="passage-head">
        <span class="passage-dot"></span>
        <span class="passage-num">${escapeHtml(summary.path)} ${escapeHtml(image.token)}</span>
        <span class="drag-tag">${escapeHtml(candidate.candidate_source || "manual")}</span>
      </div>
      <div class="image-review-copy">Edit the candidate transcription, then approve it into the placeholder position in the working copy.</div>
    `;
    const editor = document.createElement("textarea");
    editor.className = "processing-editor";
    editor.value = candidate.candidate_text || "";
    editor.placeholder = "Type or correct the image transcription...";
    state.editor = editor;
    card.appendChild(editor);
    els.passages.appendChild(card);

    const actions = document.querySelector(".hint-bar");
    actions.innerHTML = `
      <kbd>⌘↵</kbd> approve image
      <kbd>→</kbd> next item
      <kbd>←</kbd> back
      <button id="image-approve" class="pick-btn active" type="button">Approve image</button>
    `;
    $("image-approve").addEventListener("click", approveCurrentImage);
    editor.focus();
  }

  async function renderTextEditor(summary) {
    let item;
    try {
      const res = await fetch(`/api/processing/item?path=${encodeURIComponent(summary.path)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      item = await res.json();
    } catch (err) {
      return toast(`Open failed: ${err.message}`);
    }
    state.current = item;
    state.spellingEdits = [];
    els.passages.innerHTML = "";
    els.passages.appendChild(renderGlossaryPanel(item));
    els.passages.appendChild(renderSpellPanel());
    const card = document.createElement("div");
    card.className = "passage";
    const head = document.createElement("div");
    head.className = "passage-head";
    head.innerHTML = `
      <span class="passage-dot"></span>
      <span class="passage-num">${escapeHtml(item.path)}</span>
      ${item.image_count ? '<span class="drag-tag">images approved</span>' : ""}
      ${item.edited_obsidian_note ? '<span class="drag-tag">edited note</span>' : ""}
    `;

    const editor = document.createElement("textarea");
    editor.className = "processing-editor";
    editor.value = item.editable ? item.content : "This item is not editable text in Phase 2.";
    editor.disabled = !item.editable;
    state.editor = editor;

    card.appendChild(head);
    card.appendChild(editor);
    els.passages.appendChild(card);

    const actions = document.querySelector(".hint-bar");
    actions.innerHTML = `
      <kbd>⌘↵</kbd> save
      <kbd>→</kbd> next
      <kbd>←</kbd> back
      <button id="processing-save" class="pick-btn" type="button">Save</button>
    `;
    $("processing-save").disabled = !item.editable;
    $("processing-save").addEventListener("click", saveCurrent);
    editor.focus();
  }

  function renderSpellPanel() {
    const panel = document.createElement("div");
    panel.className = "spell-panel";
    panel.innerHTML = `
      <div class="spell-head">
        <div class="spell-title">Spelling</div>
        <button id="spell-run" class="pick-btn" type="button">Check spelling</button>
      </div>
      <div id="spell-list" class="spell-list">
        <div class="spell-empty">Run after glossary substitutions. Suggestions are itemized and optional.</div>
      </div>
    `;
    requestAnimationFrame(() => {
      $("spell-run")?.addEventListener("click", runSpellcheck);
    });
    return panel;
  }

  async function runSpellcheck() {
    if (!state.editor) return;
    const button = $("spell-run");
    if (button) {
      button.disabled = true;
      button.textContent = "Checking...";
    }
    try {
      const res = await fetch("/api/processing/spellcheck", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: state.editor.value }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json();
      state.spellingEdits = result.edits || [];
      renderSpellList();
    } catch (err) {
      toast(`Spellcheck failed: ${err.message}`);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "Check spelling";
      }
    }
  }

  function renderSpellList() {
    const list = $("spell-list");
    if (!list) return;
    list.innerHTML = "";
    if (!state.spellingEdits.length) {
      list.innerHTML = `<div class="spell-empty">No high-confidence spelling suggestions.</div>`;
      return;
    }
    state.spellingEdits.forEach((edit, index) => {
      const row = document.createElement("div");
      row.className = "spell-edit";
      row.innerHTML = `
        <div>
          <span class="spell-line">line ${Number(edit.line) || "?"}</span>
          <del>${escapeHtml(edit.original)}</del>
          <span aria-hidden="true"> -> </span>
          <ins>${escapeHtml(edit.suggested)}</ins>
        </div>
        <button class="pick-btn" type="button" data-accept="${index}">Accept</button>
        <button class="pick-btn" type="button" data-reject="${index}">Reject</button>
      `;
      row.querySelector("[data-accept]").addEventListener("click", () => acceptSpellEdit(index));
      row.querySelector("[data-reject]").addEventListener("click", () => rejectSpellEdit(index));
      list.appendChild(row);
    });
  }

  function acceptSpellEdit(index) {
    const edit = state.spellingEdits[index];
    if (!edit || !state.editor) return;
    const lines = state.editor.value.split("\n");
    const lineIndex = Number(edit.line) - 1;
    if (lineIndex < 0 || lineIndex >= lines.length) {
      return rejectSpellEdit(index);
    }
    const currentLine = lines[lineIndex];
    const position = currentLine.indexOf(edit.original);
    if (position === -1) {
      return rejectSpellEdit(index);
    }
    lines[lineIndex] =
      currentLine.slice(0, position) +
      edit.suggested +
      currentLine.slice(position + edit.original.length);
    state.editor.value = lines.join("\n");
    state.spellingEdits.splice(index, 1);
    renderSpellList();
    toast("Suggestion accepted");
  }

  function rejectSpellEdit(index) {
    state.spellingEdits.splice(index, 1);
    renderSpellList();
    toast("Suggestion rejected");
  }

  function renderGlossaryPanel(item) {
    const panel = document.createElement("div");
    panel.className = "glossary-panel";
    panel.innerHTML = `
      <div class="glossary-row">
        <input id="glossary-short" type="text" placeholder="dur" autocomplete="off" />
        <input id="glossary-expansion" type="text" placeholder="Duration" autocomplete="off" />
        <label class="glossary-remember"><input id="glossary-confirmed" type="checkbox" checked /> Remember</label>
        <button id="glossary-apply" class="pick-btn" type="button">Apply</button>
      </div>
      <div id="glossary-suggestions" class="glossary-suggestions"></div>
    `;
    requestAnimationFrame(() => {
      const shortInput = $("glossary-short");
      const expansionInput = $("glossary-expansion");
      const applyButton = $("glossary-apply");
      const suggestions = $("glossary-suggestions");
      applyButton.addEventListener("click", () => {
        applyGlossary(shortInput.value, expansionInput.value, $("glossary-confirmed").checked);
      });
      suggestions.innerHTML = "";
      state.glossary.forEach((entry) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "glossary-suggestion";
        button.textContent = `${entry.shorthand} -> ${entry.expansion}`;
        button.addEventListener("click", () => {
          shortInput.value = entry.shorthand;
          expansionInput.value = entry.expansion;
          applyGlossary(entry.shorthand, entry.expansion, true);
        });
        suggestions.appendChild(button);
      });
      if (!state.glossary.length) {
        suggestions.innerHTML = `<span class="processing-meta">Confirmed mappings will appear here.</span>`;
      }
    });
    return panel;
  }

  async function applyGlossary(shorthand, expansion, confirmed) {
    shorthand = String(shorthand || "").trim();
    expansion = String(expansion || "").trim();
    if (!state.current || !state.editor || !shorthand || !expansion) {
      return toast("Enter shorthand and expansion");
    }
    try {
      const saveRes = await fetch(
        `/api/processing/item?path=${encodeURIComponent(state.current.path)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: state.editor.value }),
        },
      );
      if (!saveRes.ok) throw new Error(`HTTP ${saveRes.status}`);

      const res = await fetch(
        `/api/processing/glossary-apply?path=${encodeURIComponent(state.current.path)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ shorthand, expansion, confirmed }),
        },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json();
      state.current = result.item;
      state.glossary = result.glossary || state.glossary;
      state.editor.value = result.item.content || "";
      await refreshItems();
      toast(`${result.replacement_count} replacement${result.replacement_count === 1 ? "" : "s"}`);
      await renderTextEditor(state.items[state.idx]);
    } catch (err) {
      toast(`Glossary failed: ${err.message}`);
    }
  }

  async function approveCurrentImage() {
    if (!state.currentImage || !state.editor) return;
    try {
      const res = await fetch(
        `/api/processing/image-approval?path=${encodeURIComponent(state.currentImage.path)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            index: state.currentImage.index,
            approved_text: state.editor.value,
          }),
        },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await res.json();
      await refreshItems();
    } catch (err) {
      return toast(`Approval failed: ${err.message}`);
    }
    toast("Image approved");
    await openItem(state.idx);
  }

  async function saveCurrent() {
    if (!state.current || !state.current.editable || !state.editor) return;
    try {
      const res = await fetch(
        `/api/processing/item?path=${encodeURIComponent(state.current.path)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: state.editor.value }),
        },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.current = await res.json();
      await refreshItems();
      renderList();
    } catch (err) {
      return toast(`Save failed: ${err.message}`);
    }
    toast("Saved");
  }

  function markActive() {
    document.querySelectorAll(".processing-row").forEach((row, index) => {
      row.classList.toggle("active", index === state.idx);
    });
  }

  function next() {
    if (state.idx < state.items.length - 1) openItem(state.idx + 1);
  }

  function prev() {
    if (state.idx > 0) openItem(state.idx - 1);
  }

  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      if (state.mode === "image") approveCurrentImage();
      else saveCurrent();
      return;
    }
    if (event.target && event.target.tagName === "TEXTAREA") return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      next();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      prev();
    }
  });

  let toastTimer;
  function toast(message) {
    els.toast.hidden = false;
    els.toast.textContent = message;
    requestAnimationFrame(() => els.toast.classList.add("show"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      els.toast.classList.remove("show");
      setTimeout(() => { els.toast.hidden = true; }, 220);
    }, 1500);
  }

  function showCurtain(html, isError) {
    els.curtain.hidden = false;
    els.curtainInner.innerHTML = html;
    els.curtainInner.classList.toggle("error", !!isError);
    els.split.hidden = true;
  }

  function hideCurtain() {
    els.curtain.hidden = true;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  load();
})();
"""


@app.get("/api/pages")
def api_pages(batch: str | None = None) -> dict:
    """Pages (optionally for one batch) with their passages nested."""
    pages = store.get_pages(DB, batch=batch)
    for pg in pages:
        pg["passages"] = store.get_passages(DB, pg["id"])
    return {"batch": batch, "pages": pages}


@app.get("/api/processing/items")
def api_processing_items() -> dict:
    if raw_review is None:
        raise HTTPException(503, f"Raw Data review unavailable: {_REVIEW_ERR}")
    return {"items": raw_review.list_items()}


@app.get("/api/processing/item")
def api_processing_item(path: str) -> dict:
    if raw_review is None:
        raise HTTPException(503, f"Raw Data review unavailable: {_REVIEW_ERR}")
    try:
        return raw_review.read_item(path)
    except FileNotFoundError:
        raise HTTPException(404, "processing item not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/processing/item")
def api_save_processing_item(path: str, payload: ProcessingSavePayload) -> dict:
    if raw_review is None:
        raise HTTPException(503, f"Raw Data review unavailable: {_REVIEW_ERR}")
    try:
        return raw_review.save_item(path, payload.content)
    except FileNotFoundError:
        raise HTTPException(404, "processing item not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/processing/glossary")
def api_processing_glossary() -> dict:
    if raw_review is None:
        raise HTTPException(503, f"Raw Data review unavailable: {_REVIEW_ERR}")
    return {"glossary": raw_review.glossary_entries()}


@app.post("/api/processing/glossary-apply")
def api_apply_processing_glossary(path: str, payload: GlossaryApplyPayload) -> dict:
    if raw_review is None:
        raise HTTPException(503, f"Raw Data review unavailable: {_REVIEW_ERR}")
    try:
        return raw_review.apply_glossary(
            path,
            payload.shorthand,
            payload.expansion,
            confirmed=payload.confirmed,
        )
    except FileNotFoundError:
        raise HTTPException(404, "processing item not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/processing/spellcheck")
def api_processing_spellcheck(payload: SpellcheckPayload) -> dict:
    if raw_spellcheck is None:
        raise HTTPException(503, f"Raw Data spellcheck unavailable: {_REVIEW_ERR}")
    return {"edits": raw_spellcheck.propose_spelling_fixes(payload.text)}


@app.get("/api/processing/images")
def api_processing_images(path: str) -> dict:
    if raw_images is None:
        raise HTTPException(503, f"Raw Data image review unavailable: {_REVIEW_ERR}")
    try:
        return raw_images.read_document_images(path)
    except FileNotFoundError:
        raise HTTPException(404, "processing item not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/processing/image")
def api_processing_image(path: str, index: int) -> FileResponse:
    if raw_images is None:
        raise HTTPException(503, f"Raw Data image review unavailable: {_REVIEW_ERR}")
    try:
        image_path = raw_images.image_path_for_placeholder(path, index)
    except FileNotFoundError:
        raise HTTPException(404, "image not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return FileResponse(str(image_path))


@app.get("/api/processing/image-candidate")
def api_processing_image_candidate(path: str, index: int) -> dict:
    if raw_images is None:
        raise HTTPException(503, f"Raw Data image review unavailable: {_REVIEW_ERR}")
    try:
        return raw_images.candidate_for_placeholder(path, index)
    except FileNotFoundError:
        raise HTTPException(404, "processing item not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/processing/image-approval")
def api_approve_processing_image(path: str, payload: ImageApprovalPayload) -> dict:
    if raw_images is None or raw_review is None:
        raise HTTPException(503, f"Raw Data image review unavailable: {_REVIEW_ERR}")
    try:
        image_state = raw_images.approve_placeholder(path, payload.index, payload.approved_text)
        item = raw_review.read_item(path)
    except FileNotFoundError:
        raise HTTPException(404, "processing item not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"image_state": image_state, "item": item}


@app.get("/api/image/{page_id}")
def api_image(page_id: int) -> Response:
    """Serve the *processed* page image (EXIF-corrected + downscaled) so passage
    bboxes map 1:1 onto the displayed pixels — no client-side EXIF guesswork."""
    pages = store.get_pages(DB)
    match = next((p for p in pages if p["id"] == page_id), None)
    if not match:
        raise HTTPException(404, "page not found")
    path = Path(match["image_path"])
    if not path.exists():
        raise HTTPException(404, f"image missing: {path}")
    img = images.load_image(path)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return Response(content=buf.getvalue(), media_type="image/jpeg")


@app.post("/api/page/{page_id}/save")
def api_save(page_id: int, payload: SavePayload) -> dict:
    """Persist edits + status, then flush this page's block to markdown."""
    pages = store.get_pages(DB)
    page = next((p for p in pages if p["id"] == page_id), None)
    if not page:
        raise HTTPException(404, "page not found")

    for edit in payload.passages:
        store.update_passage(DB, edit.id, edit.edited_text)
    store.update_page_number(DB, page_id, payload.page_number)
    store.update_page_author(DB, page_id, payload.author or None)
    store.update_page_status(DB, page_id, payload.status)

    # Flush markdown for accepted (reviewed) pages; discarded/retake contribute
    # nothing, but a previously-written block must be removed on re-save.
    passages = store.get_passages(DB, page_id)
    if payload.status == "reviewed":
        out_passages = passages
    else:
        out_passages = []        # empty block — page contributes no quotes
    export.append_or_update_page(
        page_id=page_id,
        batch=page["batch"],
        author=payload.author or page["author"],
        passages=out_passages,
        page_number=payload.page_number,
        output_dir=OUTPUT_DIR,
    )

    # Sync the Raw Data lake with this page's decision. Accepting publishes the
    # markdown item + moves the image in; discarding/retaking a *previously*
    # accepted page reverses that (deletes the item, returns the photo to the
    # Desktop) so the lake never holds content the user discarded. Non-fatal: a
    # lake failure must never lose the cockpit save or the local markdown flush.
    raw = None
    if publish is not None:
        try:
            if payload.status == "reviewed":
                raw = publish.publish_page(DB, page_id)
            else:
                raw = publish.unpublish_page(DB, page_id)   # no-op if never published
        except Exception as e:
            raw = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    elif payload.status == "reviewed":
        raw = {"published": False, "error": f"lake unavailable: {_PUBLISH_ERR}"}

    return {"ok": True, "status": payload.status, "raw_data": raw}


@app.post("/api/ocr-box")
def api_ocr_box(payload: OcrBoxPayload) -> dict:
    """Drag-box fallback: OCR a user-drawn crop and insert it as a new passage.

    The server loads the image via images.load_image (same EXIF-corrected +
    downscaled path used during processing) so bbox coords map 1:1 onto the
    natural image the browser displays. We always OCR the crop rather than
    intersecting against stored word boxes (those aren't persisted); this
    covers both missed highlight regions and pen-underlined pages equally.
    """
    pages = store.get_pages(DB)
    page = next((p for p in pages if p["id"] == payload.page_id), None)
    if not page:
        raise HTTPException(404, "page not found")
    path = Path(page["image_path"])
    if not path.exists():
        raise HTTPException(404, f"image missing: {path}")

    img = images.load_image(path)
    x, y, w, h = payload.bbox
    x = max(0, min(x, img.width - 1))
    y = max(0, min(y, img.height - 1))
    w = min(w, img.width - x)
    h = min(h, img.height - y)
    if w <= 0 or h <= 0:
        raise HTTPException(400, "bbox has zero area after clamping")

    crop = img.crop((x, y, x + w, y + h))
    words = ocr.ocr_page(crop)
    text = " ".join(word["text"] for word in words).strip()

    passage_id = store.insert_passage(
        DB,
        page["id"],
        bbox=[x, y, w, h],
        ocr_text=text,
        color_tag="drag",
        min_conf=None,
    )
    return {"text": text, "passage_id": passage_id}


@app.get("/api/export/csv")
def api_export_csv(batch: str) -> FileResponse:
    """Download a Readwise bulk-import CSV for all reviewed passages in a batch."""
    path = export.export_readwise_csv(DB, batch, OUTPUT_DIR)
    if path is None:
        raise HTTPException(404, f"no reviewed passages for batch '{batch}'")
    return FileResponse(
        path=str(path),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{batch}.csv"'},
    )


@app.post("/api/sample-color")
def api_sample_color(payload: SampleColorPayload) -> dict:
    """Per-batch color sampling (spec §8): median HSV of a 5×5 region around a
    click on the processed page image. The user copies the result into the
    `--hsv` CLI floor for the next process run (live reprocess is Phase 4).

    Samples `load_image(image_path)` — the same EXIF-corrected + downscaled pixels
    the cockpit displays — so the client's (x, y) in natural-image space lands on
    the pixel the user actually clicked.
    """
    path = Path(payload.image_path)
    if not path.exists():
        raise HTTPException(404, f"image missing: {path}")
    rgb = np.asarray(images.load_image(path))
    h, w = rgb.shape[:2]
    cx = max(0, min(w - 1, payload.x))
    cy = max(0, min(h - 1, payload.y))
    x1, x2 = max(0, cx - 2), min(w, cx + 3)      # 5×5 window, clamped to bounds
    y1, y2 = max(0, cy - 2), min(h, cy + 3)
    patch = cv2.cvtColor(rgb[y1:y2, x1:x2], cv2.COLOR_RGB2HSV).reshape(-1, 3)
    med = np.median(patch, axis=0)
    return {"h": int(round(med[0])), "s": int(round(med[1])), "v": int(round(med[2]))}


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
