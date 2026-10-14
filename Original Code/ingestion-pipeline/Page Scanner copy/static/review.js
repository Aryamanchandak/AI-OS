/* Agent guide: Client-side state, rendering, API calls, image overlays, drag selection, and keyboard review controls. */
/* Highlight Grabber — review cockpit logic.
   Everything shown is precomputed in the DB; this never waits on OCR.
   Loads pages, renders split-screen, drives the keyboard triage model. */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    batch: $("batch"), author: $("author"), bookMeta: $("book-meta"),
    counter: $("counter"), statusPill: $("status-pill"),
    pageNumber: $("page-number"),
    split: $("split"), passages: $("passages"),
    img: $("page-img"), overlay: $("overlay"), imageWrap: $("image-wrap"),
    curtain: $("curtain"), curtainInner: $("curtain-inner"),
    toast: $("toast"),
    pickColor: $("pick-color"), pickSwatch: $("pick-swatch"), hsvReadout: $("hsv-readout"),
    exportCsv: $("export-csv"),
  };

  const LOW_CONF = 0.5;   // line conf bottoms out AT 0.5 — flag <= , not < (see process.py)

  const state = {
    pages: [],
    idx: 0,
    boxes: [],        // current page passage bboxes (image-pixel coords)
    focusedPassage: -1,
    picking: false,   // color-sample mode active
    dragging: false,  // drag-box active
    dragStart: null,  // {x, y} in natural image coords
    dragEnd: null,
  };

  // ── Data ───────────────────────────────────────────────────────────────
  async function load() {
    const params = new URLSearchParams(location.search);
    const batch = params.get("batch");
    const url = "/api/pages" + (batch ? `?batch=${encodeURIComponent(batch)}` : "");
    let data;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (e) {
      return showCurtain(`Couldn't reach the server.<br><small>${e.message}</small>`, true);
    }
    state.pages = data.pages || [];
    if (!state.pages.length) {
      return showCurtain("No pages in the database yet.<br><small>Run <code>process.py</code> on your inbox first.</small>", false);
    }
    // Resume at the first un-reviewed page.
    const firstNew = state.pages.findIndex((p) => p.status === "new");
    state.idx = firstNew === -1 ? 0 : firstNew;
    hideCurtain();
    els.split.hidden = false;
    render();
  }

  // ── Render ─────────────────────────────────────────────────────────────
  // Resolved book metadata (year · isbn · source/confidence), from ingest. A
  // low/none confidence match is flagged so you can fix .book.json before it
  // hardens into the Raw Data lake.
  function renderBookMeta(page) {
    let m = null;
    try { m = page.book_meta ? JSON.parse(page.book_meta) : null; } catch (_) { m = null; }
    if (!m) { els.bookMeta.hidden = true; return; }
    const bits = [];
    if (m.year) bits.push(m.year);
    if (m.isbn) bits.push(`ISBN ${m.isbn}`);
    if (m.confidence) bits.push(m.confidence);
    els.bookMeta.textContent = bits.join(" · ");
    const weak = m.confidence === "low" || m.confidence === "none";
    els.bookMeta.classList.toggle("weak", weak);
    els.bookMeta.title = weak ? "Low-confidence match — check .book.json" : "";
    els.bookMeta.hidden = bits.length === 0;
  }

  function render() {
    const page = state.pages[state.idx];
    if (!page) return;

    els.batch.textContent = page.batch || "—";
    els.author.value = page.author || "";
    renderBookMeta(page);
    els.exportCsv.hidden = !page.batch;
    els.counter.textContent = `${state.idx + 1} / ${state.pages.length}`;
    setStatusPill(page.status);
    els.pageNumber.value = page.page_number ?? "";

    // Image (processed → bbox coords map 1:1).
    els.overlay.getContext("2d").clearRect(0, 0, els.overlay.width, els.overlay.height);
    els.img.src = `/api/image/${page.id}`;

    // Passages.
    state.boxes = [];
    state.focusedPassage = -1;
    els.passages.innerHTML = "";
    const passages = page.passages || [];
    if (!passages.length) {
      const note = document.createElement("div");
      note.className = "empty-note";
      note.textContent = "No highlighted passages detected on this page.";
      els.passages.appendChild(note);
    }
    passages.forEach((p, i) => {
      state.boxes.push(p.bbox);
      const lowConf = p.min_conf != null && p.min_conf <= LOW_CONF;

      const card = document.createElement("div");
      card.className = "passage" + (lowConf ? " low-conf" : "");
      card.style.animationDelay = `${i * 45}ms`;

      const head = document.createElement("div");
      head.className = "passage-head";
      head.innerHTML = `<span class="passage-dot"></span><span class="passage-num">Passage ${i + 1}</span>`;
      if (lowConf) {
        const warn = document.createElement("span");
        warn.className = "lowconf-tag";
        warn.textContent = "⚠ low confidence";
        head.appendChild(warn);
      }

      const ta = document.createElement("textarea");
      ta.value = p.edited_text ?? p.ocr_text ?? "";
      ta.dataset.passageId = p.id;
      ta.dataset.index = i;
      ta.rows = 2;
      autosize(ta);
      ta.addEventListener("input", () => autosize(ta));
      ta.addEventListener("focus", () => { state.focusedPassage = i; drawBoxes(); });
      ta.addEventListener("blur", () => { state.focusedPassage = -1; drawBoxes(); });

      card.appendChild(head);
      card.appendChild(ta);
      els.passages.appendChild(card);
    });
  }

  function autosize(ta) {
    ta.style.height = "auto";
    ta.style.height = Math.max(64, ta.scrollHeight) + "px";
  }

  function setStatusPill(status) {
    els.statusPill.textContent = status;
    els.statusPill.dataset.status = status;
  }

  // ── Overlay drawing ────────────────────────────────────────────────────
  els.img.addEventListener("load", () => {
    sizeOverlay();
    drawBoxes();
  });
  window.addEventListener("resize", () => { sizeOverlay(); drawBoxes(); });

  function sizeOverlay() {
    const w = els.img.clientWidth, h = els.img.clientHeight;
    els.overlay.width = w;
    els.overlay.height = h;
    els.overlay.style.width = w + "px";
    els.overlay.style.height = h + "px";
  }

  function drawBoxes() {
    const ctx = els.overlay.getContext("2d");
    ctx.clearRect(0, 0, els.overlay.width, els.overlay.height);
    if (!els.img.naturalWidth) return;
    const sx = els.img.clientWidth / els.img.naturalWidth;
    const sy = els.img.clientHeight / els.img.naturalHeight;
    state.boxes.forEach((b, i) => {
      if (!b) return;
      const [x, y, w, h] = b;
      const active = i === state.focusedPassage;
      ctx.fillStyle = active ? "rgba(217,148,5,0.28)" : "rgba(232,176,32,0.18)";
      ctx.strokeStyle = active ? "rgba(217,148,5,0.95)" : "rgba(217,148,5,0.55)";
      ctx.lineWidth = active ? 2.5 : 1.5;
      const rx = x * sx, ry = y * sy, rw = w * sx, rh = h * sy;
      roundRect(ctx, rx - 2, ry - 2, rw + 4, rh + 4, 4);
      ctx.fill();
      ctx.stroke();
    });
    // Rubber-band drag rect
    if (state.dragging && state.dragStart && state.dragEnd) {
      const rx = Math.min(state.dragStart.x, state.dragEnd.x) * sx;
      const ry = Math.min(state.dragStart.y, state.dragEnd.y) * sy;
      const rw = Math.abs(state.dragEnd.x - state.dragStart.x) * sx;
      const rh = Math.abs(state.dragEnd.y - state.dragStart.y) * sy;
      if (rw > 0 && rh > 0) {
        ctx.strokeStyle = "rgba(58, 109, 168, 0.9)";
        ctx.fillStyle = "rgba(58, 109, 168, 0.08)";
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 3]);
        ctx.strokeRect(rx, ry, rw, rh);
        ctx.fillRect(rx, ry, rw, rh);
        ctx.setLineDash([]);
      }
    }
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // ── Save / navigate ────────────────────────────────────────────────────
  function collectEdits() {
    return [...els.passages.querySelectorAll("textarea")].map((ta) => ({
      id: Number(ta.dataset.passageId),
      edited_text: ta.value,
    }));
  }

  function currentPageNumber() {
    const v = els.pageNumber.value.trim();
    return v === "" ? null : Number(v);
  }

  async function save(status, { advance = true } = {}) {
    const page = state.pages[state.idx];
    if (!page) return;
    const edits = collectEdits();
    const pageNumber = currentPageNumber();
    const author = els.author.value.trim() || null;
    try {
      const res = await fetch(`/api/page/${page.id}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passages: edits, page_number: pageNumber, author, status }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (e) {
      return toast(`Save failed: ${e.message}`);
    }
    // Reflect locally so re-visiting shows the latest.
    page.status = status;
    page.page_number = pageNumber;
    page.author = author;
    edits.forEach((ed) => {
      const p = (page.passages || []).find((pp) => pp.id === ed.id);
      if (p) p.edited_text = ed.edited_text;
    });
    setStatusPill(status);
    toast(LABEL[status] || "Saved");
    if (advance) next();
  }

  const LABEL = {
    reviewed: "Accepted →", discarded: "Discarded →", retake: "Flagged for retake →",
  };

  function next() {
    if (state.idx < state.pages.length - 1) { state.idx++; render(); }
    else { toast("End of queue 🎉"); }
  }
  function prev() {
    if (state.idx > 0) { state.idx--; render(); }
  }

  // ── Keyboard model ─────────────────────────────────────────────────────
  function inTextarea(e) {
    const t = e.target;
    return t && (t.tagName === "TEXTAREA");
  }
  function inAnyField(e) {
    const t = e.target;
    return t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT");
  }

  document.addEventListener("keydown", (e) => {
    // Cmd/Ctrl+Enter — accept + advance, works from anywhere (incl. textarea).
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      save("reviewed");
      return;
    }
    // Single-key shortcuts fire only when NOT editing text.
    if (inAnyField(e)) return;
    switch (e.key) {
      case "ArrowRight": e.preventDefault(); next(); break;          // skip, no save
      case "ArrowLeft":  e.preventDefault(); prev(); break;          // back (editable)
      case "d": e.preventDefault(); save("discarded"); break;
      case "f": e.preventDefault(); save("retake"); break;
    }
  });

  // ── UI helpers ─────────────────────────────────────────────────────────
  let toastTimer;
  function toast(msg) {
    els.toast.hidden = false;
    els.toast.textContent = msg;
    requestAnimationFrame(() => els.toast.classList.add("show"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      els.toast.classList.remove("show");
      setTimeout(() => { els.toast.hidden = true; }, 220);
    }, 1500);
  }

  // ── Per-batch color sampling (spec §8) ─────────────────────────────────
  function setPicking(on) {
    state.picking = on;
    els.imageWrap.classList.toggle("picking", on);
    els.pickColor.classList.toggle("active", on);
    if (on) toast("Click the highlighter on the page");
  }

  els.pickColor.addEventListener("click", () => setPicking(!state.picking));

  els.exportCsv.addEventListener("click", () => {
    const page = state.pages[state.idx];
    if (!page || !page.batch) return;
    window.open(`/api/export/csv?batch=${encodeURIComponent(page.batch)}`);
  });

  els.img.addEventListener("click", async (e) => {
    if (!state.picking) return;
    const page = state.pages[state.idx];
    if (!page || !els.img.naturalWidth) return;
    // Display coords → natural-image pixel coords (same space the server samples).
    const nx = Math.round(e.offsetX * els.img.naturalWidth / els.img.clientWidth);
    const ny = Math.round(e.offsetY * els.img.naturalHeight / els.img.clientHeight);
    try {
      const res = await fetch("/api/sample-color", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_path: page.image_path, x: nx, y: ny }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { h, s, v } = await res.json();
      showHsv(h, s, v);
    } catch (err) {
      toast(`Color sample failed: ${err.message}`);
    } finally {
      setPicking(false);
    }
  });

  function showHsv(h, s, v) {
    const arg = `${h},${s},${v}`;
    els.hsvReadout.hidden = false;
    els.hsvReadout.textContent = `--hsv ${arg}`;
    // Preview swatch (HSV is OpenCV scale: H∈[0,179]); convert for CSS.
    els.pickSwatch.style.background = `hsl(${h * 2} ${Math.round(s / 2.55)}% ${Math.round(v / 2.55 * 0.6 + 20)}%)`;
    els.hsvReadout.onclick = () => {
      navigator.clipboard?.writeText(arg);
      toast(`Copied ${arg}`);
    };
    toast(`Sampled HSV ${arg}`);
  }

  // ── Drag-box fallback (spec §7 + Phase 3) ─────────────────────────────
  // Drag on the page image → rubber-band rect → crop OCR → new passage field.
  // Covers missed highlight regions and pen-underlined pages.

  function clientToNaturalCoords(clientX, clientY) {
    const rect = els.img.getBoundingClientRect();
    const dx = Math.max(0, Math.min(rect.width, clientX - rect.left));
    const dy = Math.max(0, Math.min(rect.height, clientY - rect.top));
    if (!els.img.naturalWidth) return { nx: 0, ny: 0 };
    return {
      nx: Math.round(dx * els.img.naturalWidth / rect.width),
      ny: Math.round(dy * els.img.naturalHeight / rect.height),
    };
  }

  els.img.addEventListener("mousedown", (e) => {
    if (state.picking) return;
    if (!state.pages[state.idx]) return;
    e.preventDefault();
    const { nx, ny } = clientToNaturalCoords(e.clientX, e.clientY);
    state.dragging = true;
    state.dragStart = { x: nx, y: ny };
    state.dragEnd = { x: nx, y: ny };
    els.imageWrap.classList.add("dragging");
  });

  document.addEventListener("mousemove", (e) => {
    if (!state.dragging) return;
    const { nx, ny } = clientToNaturalCoords(e.clientX, e.clientY);
    state.dragEnd = { x: nx, y: ny };
    drawBoxes();
  });

  document.addEventListener("mouseup", async (e) => {
    if (!state.dragging) return;
    state.dragging = false;
    els.imageWrap.classList.remove("dragging");
    const { dragStart, dragEnd } = state;
    state.dragStart = null;
    state.dragEnd = null;
    drawBoxes();

    if (!dragStart || !dragEnd) return;
    const x = Math.min(dragStart.x, dragEnd.x);
    const y = Math.min(dragStart.y, dragEnd.y);
    const w = Math.abs(dragEnd.x - dragStart.x);
    const h = Math.abs(dragEnd.y - dragStart.y);
    if (w < 10 || h < 10) return;   // too small — treat as a click, ignore

    await submitDragBox([x, y, w, h]);
  });

  async function submitDragBox(bbox) {
    const page = state.pages[state.idx];
    if (!page) return;
    toast("OCR-ing selection…");

    let result;
    try {
      const res = await fetch("/api/ocr-box", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          page_id: page.id,
          bbox: bbox.map(Math.round),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      result = await res.json();
    } catch (err) {
      return toast(`OCR failed: ${err.message}`);
    }

    const { text, passage_id } = result;
    const newPassage = { id: passage_id, bbox, ocr_text: text, edited_text: text, min_conf: null };
    (page.passages = page.passages || []).push(newPassage);
    state.boxes.push(bbox);
    drawBoxes();

    // Remove empty-note placeholder if present.
    const emptyNote = els.passages.querySelector(".empty-note");
    if (emptyNote) emptyNote.remove();

    const passageIndex = state.boxes.length - 1;
    const card = document.createElement("div");
    card.className = "passage";
    card.style.animationDelay = "0ms";

    const head = document.createElement("div");
    head.className = "passage-head";
    head.innerHTML =
      `<span class="passage-dot"></span>` +
      `<span class="passage-num">Passage ${passageIndex + 1} <span class="drag-tag">drag</span></span>`;

    const ta = document.createElement("textarea");
    ta.value = text;
    ta.dataset.passageId = passage_id;
    ta.dataset.index = passageIndex;
    ta.rows = 2;
    autosize(ta);
    ta.addEventListener("input", () => autosize(ta));
    ta.addEventListener("focus", () => { state.focusedPassage = passageIndex; drawBoxes(); });
    ta.addEventListener("blur",  () => { state.focusedPassage = -1;           drawBoxes(); });

    card.appendChild(head);
    card.appendChild(ta);
    els.passages.appendChild(card);
    card.scrollIntoView({ behavior: "smooth", block: "end" });
    ta.focus();

    toast("Selection added — type to fix, ⌘↵ to accept");
  }

  function showCurtain(html, isError) {
    els.curtain.hidden = false;
    els.curtainInner.innerHTML = html;
    els.curtainInner.classList.toggle("error", !!isError);
    els.split.hidden = true;
  }
  function hideCurtain() { els.curtain.hidden = true; }

  load();
})();
