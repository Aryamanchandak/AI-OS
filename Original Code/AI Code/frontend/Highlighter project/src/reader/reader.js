import { getValue, setValue, setValues, updateValues } from "../db.js";

/* ============================================================
   0. tiny helpers
   ============================================================ */
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let toastT;
function toast(msg){
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2200);
}
async function sget(k){ try{ return (await getValue(k)) ?? null; }catch(e){ console.warn('storage read', e); throw e; } }
async function sset(k,v){ try{ await setValue(k, v); }catch(e){ console.warn('storage write', e); throw e; } }

/* ============================================================
   1. sanitizer — allowlist only. Capture is untrusted input.
   ============================================================ */
const ALLOW = {
  p:[],h1:[],h2:[],h3:[],h4:[],ul:[],ol:[],li:[],blockquote:[],pre:[],code:[],
  em:[],i:[],strong:[],b:[],u:[],s:[],sup:[],sub:[],br:[],hr:[],figure:[],figcaption:[],
  a:['href'],img:['src','alt'],table:[],thead:[],tbody:[],tr:[],th:[],td:[]
};
function sanitize(html){
  const t = document.createElement('template'); t.innerHTML = html;
  (function walk(node){
    for (const child of Array.from(node.childNodes)){
      if (child.nodeType === 3) continue;
      if (child.nodeType !== 1){ child.remove(); continue; }
      const tag = child.tagName.toLowerCase();
      if (!(tag in ALLOW)){
        // unwrap unknown containers, drop scripts/styles outright
        if (['script','style','noscript','iframe','object','svg','canvas'].includes(tag)) child.remove();
        else { walk(child); child.replaceWith(...child.childNodes); }
        continue;
      }
      for (const a of Array.from(child.attributes)){
        if (!ALLOW[tag].includes(a.name)) child.removeAttribute(a.name);
      }
      const href = child.getAttribute && child.getAttribute('href');
      if (href && /^\s*(javascript|data):/i.test(href)) child.removeAttribute('href');
      const src = child.getAttribute && child.getAttribute('src');
      if (src && /^\s*(javascript|data):/i.test(src)) child.remove();
      else walk(child);
    }
  })(t.content);
  return t.innerHTML;
}
/* Plain text -> blocks, for pasted prose */
function textToHtml(txt){
  return txt.split(/\n{2,}/).map(p => {
    const s = p.trim(); if (!s) return '';
    if (/^#{1,3}\s/.test(s)) { const n = s.match(/^#+/)[0].length; return `<h${n}>${esc(s.replace(/^#+\s/,''))}</h${n}>`; }
    if (/^[-*]\s/m.test(s) && s.split('\n').every(l => /^[-*]\s/.test(l.trim())))
      return '<ul>' + s.split('\n').map(l => `<li>${esc(l.replace(/^\s*[-*]\s/,''))}</li>`).join('') + '</ul>';
    return `<p>${esc(s).replace(/\n/g,' ')}</p>`;
  }).join('');
}
function hash(str){
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

/* ============================================================
   2. state
   ============================================================ */
const BLOCK_TAGS = 'h1,h2,h3,h4,p,li,blockquote,pre,figcaption,tr';
let S = {
  docs: [],          // [{id,title,url,capturedAt,revisionHash}]
  doc: null,         // full doc {..., html}
  hls: [],           // highlights for current doc
  canonical: '',     // canonical text of current doc
  index: [],         // [{node,start,end,blockId,blockOffset}] over the PAINTED dom
  blocks: [],        // [{id,el,start,end}]
  focus: -1,
  active: null,      // active highlight id
  undo: [],
  auto: true,
  dragging: null,     // active resize transaction; the DOM grip itself is disposable
  suppressSelectionUntil: 0
};
let saveQueue = Promise.resolve();

/* ============================================================
   3. render + index
   The DOM is derived from doc.html every single time.
   Nothing mutates the stored html, ever.
   ============================================================ */
function renderDocument(){
  const d = S.doc, host = $('#doc');
  const sourceUrl = safeHttpUrl(d.url);
  host.innerHTML =
    `<h1 data-block-id="title">${esc(d.title)}</h1>` +
    `<div class="docmeta">${sourceUrl ? `<a href="${esc(sourceUrl)}" target="_blank" rel="noopener noreferrer">${esc(hostname(sourceUrl))}</a>` : '<span>pasted</span>'}` +
    `<span>frozen ${new Date(d.capturedAt).toLocaleDateString()}</span><span class="strat">rev ${d.revisionHash}</span></div>` +
    d.html;
  normalizeTextNodes(host);
  indexDocument();
}
function hostname(u){ try{ return new URL(u).hostname.replace(/^www\./,''); }catch(e){ return u; } }
function safeHttpUrl(value){
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : '';
  } catch { return ''; }
}

/* NBSP and composed forms are normalised once, in the DOM itself, so the
   canonical string and the live text nodes can never drift apart. */
function normalizeTextNodes(root){
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n, list = [];
  while ((n = w.nextNode())) list.push(n);
  for (const t of list){
    const v = t.nodeValue.replace(/\u00a0/g, ' ').normalize('NFC');
    if (v !== t.nodeValue) t.nodeValue = v;
  }
}

function indexDocument(){
  S.index = []; S.blocks = [];
  let text = '', pos = 0;

  // Block ids are assigned by document order over a fixed selector, and the
  // document is rebuilt from the same frozen html every time — so they are stable.
  const all = Array.from($('#doc').querySelectorAll(BLOCK_TAGS + ',[data-block-id]'));
  all.forEach((el, i) => { if (!el.dataset.blockId) el.dataset.blockId = 'b' + i; });

  // only leaf blocks carry text (a blockquote wrapping a p is not itself a block)
  const ordered = all.filter(el => !el.querySelector(BLOCK_TAGS + ',[data-block-id]'));
  for (const el of ordered){
    const bStart = pos;
    // UI we inject into the document (note glyphs, margin notes) is not content
    // and must never enter the canonical string, or every later offset shifts.
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode: n => n.parentElement && n.parentElement.closest('.glyph,.marginnote,.grip')
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
    });
    let n, bOff = 0;
    while ((n = w.nextNode())){
      const len = n.nodeValue.length;
      if (len === 0) continue;
      S.index.push({ node:n, start:pos, end:pos+len, blockId:el.dataset.blockId, blockOffset:bOff });
      text += n.nodeValue; pos += len; bOff += len;
    }
    S.blocks.push({ id: el.dataset.blockId, el, start: bStart, end: pos });
    text += '\n'; pos += 1;
  }
  S.canonical = text;
}

/* offset <-> DOM */
function globalOf(node, offset){
  const e = S.index.find(x => x.node === node);
  if (e) return e.start + Math.min(offset, e.end - e.start);
  // Container boundaries are common beside inline elements. Prefer the first
  // indexed descendant after the caret, then the last one before it.
  if (node.nodeType === 1){
    const kids = Array.from(node.childNodes);
    const entriesIn = child => child ? S.index.filter(x => x.node === child || (child.nodeType === 1 && child.contains(x.node))) : [];
    const after = entriesIn(kids[offset]);
    if (after.length) return after[0].start;
    const before = entriesIn(kids[offset - 1]);
    if (before.length) return before[before.length - 1].end;
    const inside = S.index.filter(x => node.contains(x.node));
    if (inside.length) return offset <= 0 ? inside[0].start : inside[inside.length - 1].end;
  }
  return null;
}
function partsFor(start, end){
  return S.index
    .filter(e => e.end > start && e.start < end)
    .map(e => ({ node:e.node, s: Math.max(0, start - e.start), e: Math.min(e.end - e.start, end - e.start) }))
    .filter(p => p.e > p.s);
}
function blockAt(off){ return S.blocks.find(b => off >= b.start && off <= b.end) || S.blocks[0]; }

/* ============================================================
   4. painting — disposable by design
   ============================================================ */
function repaint(){
  const wasActive = S.active;
  renderDocument();                       // wipes every wrapper, restores original text
  const placed = S.hls.filter(h => h.status === 'attached').sort((a,b) => a.position.start - b.position.start);
  // paint in reverse document order so earlier text-node offsets stay valid
  for (let i = placed.length - 1; i >= 0; i--) paint(placed[i]);
  indexDocument();
  S.active = wasActive;
  if (S.active) markActive(S.active);
  layoutMarginNotes();
  renderNotebook();
}
function paint(h){
  const parts = partsFor(h.position.start, h.position.end);
  for (let i = parts.length - 1; i >= 0; i--){
    const p = parts[i];
    const r = document.createRange();
    try { r.setStart(p.node, p.s); r.setEnd(p.node, p.e); } catch(e){ continue; }
    const el = document.createElement('rw-highlight');
    el.dataset.highlightId = h.id;
    if (i === 0){
      el.tabIndex = 0;
      el.setAttribute('role', 'button');
      el.setAttribute('aria-label', `Open highlight actions: ${h.quote.exact.slice(0, 120)}`);
    }
    if (h.note) el.classList.add('has-note');
    try { r.surroundContents(el); } catch(e){ continue; }
    if (i === 0){
      const g = makeGrip('start');
      el.insertBefore(g, el.firstChild);
    }
    if (i === parts.length - 1){
      const g = makeGrip('end');
      el.appendChild(g);
      if (h.note || (h.tags && h.tags.length)){
        const s = document.createElement('span'); s.className = 'glyph';
        s.textContent = (h.note ? '✎' : '') + (h.tags && h.tags.length ? '#' : '');
        el.appendChild(s);
      }
    }
  }
}
function makeGrip(edge){
  const g = document.createElement('button');
  g.type = 'button';
  g.className = 'grip ' + (edge === 'start' ? 's' : 'e');
  g.dataset.edge = edge;
  g.setAttribute('aria-label', `Resize ${edge} boundary`);
  g.title = `Drag to resize the ${edge} boundary · Arrow keys nudge`;
  return g;
}
function markActive(id){
  $$('rw-highlight.active').forEach(e => e.classList.remove('active'));
  $$(`rw-highlight[data-highlight-id="${id}"]`).forEach(e => e.classList.add('active'));
}
function layoutMarginNotes(){
  $$('.marginnote').forEach(e => e.remove());
  if (window.innerWidth < 1360) return;
  for (const h of S.hls){
    if (!h.note || h.status !== 'attached') continue;
    const el = document.querySelector(`rw-highlight[data-highlight-id="${h.id}"]`);
    if (!el) continue;
    const block = el.closest('[data-block-id]'); if (!block) continue;
    const note = document.createElement('div');
    note.className = 'marginnote'; note.textContent = h.note;
    note.style.top = (el.offsetTop - block.offsetTop) + 'px';
    block.appendChild(note);
  }
}

/* ============================================================
   5. creating highlights
   ============================================================ */
const CTX = 40;
function trimBounds(start, end){
  while (start < end && /\s/.test(S.canonical[start])) start++;
  while (end > start && /\s/.test(S.canonical[end - 1])) end--;
  return { start, end };
}
function refreshAnchors(h, start, end, opts = {}){
  const sb = blockAt(start), eb = blockAt(end);
  h.position = { start, end };
  h.quote = {
    exact: S.canonical.slice(start, end),
    prefix: S.canonical.slice(Math.max(0, start - CTX), start),
    suffix: S.canonical.slice(end, end + CTX)
  };
  h.range = {
    startBlockId: sb.id, startOffset: start - sb.start,
    endBlockId: eb.id, endOffset: end - eb.start
  };
  h.revisionHash = S.doc.revisionHash;
  h.status = 'attached';
  if (opts.strategy) h.strategy = opts.strategy;
  if (opts.confidence != null) h.confidence = opts.confidence;
  if (opts.touchUpdatedAt) h.updatedAt = new Date().toISOString();
  return h;
}
function makeHighlight(start, end){
  // trim whitespace at the edges — nobody means to highlight a trailing space
  ({ start, end } = trimBounds(start, end));
  if (end - start < 1) return null;

  return refreshAnchors({
    id: uid(),
    docId: S.doc.id,
    revisionHash: S.doc.revisionHash,
    note: '', tags: [],
    createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
    status: 'attached', strategy: 'created', confidence: 1
  }, start, end);
}
/* merge rule lives at the DATA layer, not the render layer.
   overlapping or touching (<=1 whitespace apart) highlights become one record. */
function shouldMerge(a, b){
  if (a.status !== 'attached' || b.status !== 'attached') return false;
  const left = a.position.start <= b.position.start ? a : b;
  const right = left === a ? b : a;
  if (left.position.end >= right.position.start) return true;
  const gap = S.canonical.slice(left.position.end, right.position.start);
  return gap.length === 1 && /\s/.test(gap);
}
function mergeRecords(a, b){
  const aFirst = (a.createdAt || '') <= (b.createdAt || '');
  const older = aFirst ? a : b;
  const newer = aFirst ? b : a;
  const start = Math.min(a.position.start, b.position.start);
  const end = Math.max(a.position.end, b.position.end);
  const directStrategy = a.strategy === 'resized' || b.strategy === 'resized' ? 'resized' : (newer.strategy || older.strategy);
  return refreshAnchors({
    ...older,
    note: [older.note, newer.note].filter(Boolean).join('\n'),
    tags: Array.from(new Set([...(older.tags || []), ...(newer.tags || [])])),
    updatedAt: new Date().toISOString()
  }, start, end, { strategy: directStrategy, confidence: 1 });
}
function mergeIntoStore(candidate){
  let merged = candidate;
  let rest = S.hls.filter(x => x.id !== candidate.id);
  // The union can grow far enough to reach a record seen earlier, so repeat
  // until no remaining record violates the store invariant.
  let changed = true;
  while (changed){
    changed = false;
    const keep = [];
    for (const x of rest){
      if (shouldMerge(x, merged)){
        merged = mergeRecords(x, merged);
        changed = true;
      } else keep.push(x);
    }
    rest = keep;
  }
  S.hls = [...rest, merged];
  return merged;
}
function commit(h, undoSnapshot){
  if (!h) return null;
  pushUndo(undoSnapshot);
  const merged = mergeIntoStore(h);
  S.active = merged.id;
  save(); repaint();
  return merged;
}
function pushUndo(snapshot = JSON.stringify(S.hls)){
  S.undo.push(snapshot);
  if (S.undo.length > 60) S.undo.shift();
}
function undo(){
  if (!S.undo.length) return toast('Nothing to undo');
  S.hls = JSON.parse(S.undo.pop());
  S.active = null; save(); repaint(); toast('Undone');
}

/* selection -> highlight */
document.addEventListener('mouseup', e => {
  if (S.dragging || Date.now() < S.suppressSelectionUntil) return;
  setTimeout(() => handleSelection(e.altKey), 0);
});
document.addEventListener('keyup', e => { if (e.key === 'Shift') handleSelection(false); });
function handleSelection(bypass){
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !S.auto || bypass) return;
  const r = sel.getRangeAt(0);
  if (!$('#doc').contains(r.commonAncestorContainer)) return;
  const a = globalOf(r.startContainer, r.startOffset);
  const b = globalOf(r.endContainer, r.endOffset);
  if (a == null || b == null) return;
  const h = commit(makeHighlight(Math.min(a,b), Math.max(a,b)));
  sel.removeAllRanges();
  if (h) showTools(h.id);
}

/* click an existing mark */
$('#doc').addEventListener('click', e => {
  const el = e.target.closest && e.target.closest('rw-highlight');
  if (el){ S.active = el.dataset.highlightId; markActive(S.active); showTools(S.active); renderNotebook(); }
  else if (!e.target.closest('.tools') && !e.target.closest('.pop')) hideTools();
});
$('#doc').addEventListener('keydown', e => {
  const el = e.target.closest && e.target.closest('rw-highlight');
  if (!el || (e.key !== 'Enter' && e.key !== ' ')) return;
  e.preventDefault();
  S.active = el.dataset.highlightId;
  markActive(S.active);
  showTools(S.active);
  renderNotebook();
  $('#tools button')?.focus();
});

/* ============================================================
   6. resize grips
   ============================================================ */
document.addEventListener('pointerdown', e => {
  const g = e.target.closest && e.target.closest('.grip');
  if (!g) return;
  if (e.pointerType === 'mouse' && e.button !== 0) return;
  const mark = g.closest('rw-highlight');
  const h = mark && S.hls.find(x => x.id === mark.dataset.highlightId);
  if (!h || h.status !== 'attached') return;
  e.preventDefault();
  e.stopPropagation();
  S.dragging = {
    id: h.id,
    edge: g.dataset.edge,
    pointerId: e.pointerId,
    before: JSON.stringify(S.hls),
    original: { ...h.position },
    changed: false
  };
  S.suppressSelectionUntil = Date.now() + 500;
  document.body.classList.add('resizing');
  try { $('#doc').setPointerCapture(e.pointerId); } catch(err){}
  hideTools();
});
document.addEventListener('pointermove', e => {
  if (!S.dragging || e.pointerId !== S.dragging.pointerId) return;
  e.preventDefault();
  const off = offsetFromPoint(e.clientX, e.clientY);
  if (off == null) return;
  previewResize(off);
});
document.addEventListener('pointerup', e => {
  if (!S.dragging || e.pointerId !== S.dragging.pointerId) return;
  e.preventDefault();
  finishResize(true);
});
document.addEventListener('pointercancel', e => {
  if (!S.dragging || e.pointerId !== S.dragging.pointerId) return;
  finishResize(false);
});
$('#doc').addEventListener('lostpointercapture', e => {
  if (S.dragging && e.pointerId === S.dragging.pointerId) finishResize(false);
});
function resizeBounds(h, edge, rawOffset){
  const lastBlock = S.blocks[S.blocks.length - 1];
  const docEnd = lastBlock ? lastBlock.end : S.canonical.length;
  const off = Math.max(0, Math.min(docEnd, rawOffset));
  let { start, end } = h.position;
  if (edge === 'start') start = Math.min(off, stepCodePoint(end, -1));
  else end = Math.max(off, stepCodePoint(start, 1));
  return { start, end };
}
function previewResize(off){
  const tx = S.dragging; if (!tx) return false;
  const h = S.hls.find(x => x.id === tx.id); if (!h) return false;
  const { start, end } = resizeBounds(h, tx.edge, off);
  if (start === h.position.start && end === h.position.end) return false;
  refreshAnchors(h, start, end, { strategy: 'resized', confidence: 1 });
  tx.changed = true;
  repaint(); markActive(h.id);
  return true;
}
function finishResize(shouldCommit, announceCancel = false){
  const tx = S.dragging; if (!tx) return null;
  S.dragging = null; // clear first: releasePointerCapture emits lostpointercapture
  document.body.classList.remove('resizing');
  try {
    if ($('#doc').hasPointerCapture(tx.pointerId)) $('#doc').releasePointerCapture(tx.pointerId);
  } catch(err){}

  const restore = () => {
    S.hls = JSON.parse(tx.before);
    S.active = tx.id;
    repaint();
    requestAnimationFrame(() => {
      focusGrip(tx.id, tx.edge);
      showTools(tx.id);
    });
    if (announceCancel) toast('Resize cancelled');
    return null;
  };
  if (!shouldCommit || !tx.changed) return restore();

  const h = S.hls.find(x => x.id === tx.id);
  if (!h) return restore();
  const bounds = trimBounds(h.position.start, h.position.end);
  if (bounds.end <= bounds.start ||
      (bounds.start === tx.original.start && bounds.end === tx.original.end)) return restore();

  refreshAnchors(h, bounds.start, bounds.end, {
    strategy: 'resized', confidence: 1, touchUpdatedAt: true
  });
  const merged = commit(h, tx.before);
  requestAnimationFrame(() => {
    focusGrip(merged.id, tx.edge);
    showTools(merged.id);
  });
  return merged;
}
function focusGrip(id, edge){
  const side = edge === 'start' ? 's' : 'e';
  document.querySelector(`rw-highlight[data-highlight-id="${id}"] .grip.${side}`)?.focus({ preventScroll:true });
}
function offsetFromPoint(x, y){
  let node, offset;
  if (document.caretPositionFromPoint){
    const p = document.caretPositionFromPoint(x, y); if (!p) return null;
    node = p.offsetNode; offset = p.offset;
  } else if (document.caretRangeFromPoint){
    const r = document.caretRangeFromPoint(x, y); if (!r) return null;
    node = r.startContainer; offset = r.startOffset;
  } else return null;
  const grip = node.nodeType === 1 ? node.closest?.('.grip') : node.parentElement?.closest('.grip');
  if (grip){
    const mark = grip.closest('rw-highlight');
    const h = mark && S.hls.find(v => v.id === mark.dataset.highlightId);
    if (h) return grip.dataset.edge === 'start' ? h.position.start : h.position.end;
  }
  if (!$('#doc').contains(node)) return null;
  return globalOf(node, offset);
}

/* ============================================================
   7. keyboard grammar
   ============================================================ */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && S.dragging){
    e.preventDefault();
    finishResize(false, true);
    return;
  }
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
  if (e.metaKey || e.ctrlKey) return;
  const grip = e.target.closest && e.target.closest('.grip');
  if (grip && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')){
    e.preventDefault();
    resizeFromKeyboard(grip, e.key, e.shiftKey ? 5 : 1);
    return;
  }
  const k = e.key.toLowerCase();
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp'){
    if (!S.blocks.length) return;
    e.preventDefault();
    S.focus = Math.max(0, Math.min(S.blocks.length - 1, S.focus + (e.key === 'ArrowDown' ? 1 : -1)));
    paintFocus();
  } else if (k === 'h' || k === 'n'){
    if (S.focus < 0) return;
    e.preventDefault();
    const b = S.blocks[S.focus];
    const h = commit(makeHighlight(b.start, b.end));
    if (h && k === 'n') openPop(h.id, 'note');
  } else if (k === 't'){
    if (!S.active) return;
    e.preventDefault(); openPop(S.active, 'tag');
  } else if (k === 'z'){
    e.preventDefault(); undo();
  } else if (e.key === 'Escape'){
    hideTools(); closePop(); S.active = null; markActive(''); renderNotebook();
  }
});
function stepCodePoint(off, direction){
  if (direction < 0){
    if (off <= 0) return 0;
    let next = off - 1;
    const low = S.canonical.charCodeAt(next);
    const high = S.canonical.charCodeAt(next - 1);
    if (low >= 0xDC00 && low <= 0xDFFF && high >= 0xD800 && high <= 0xDBFF) next--;
    return next;
  }
  if (off >= S.canonical.length) return S.canonical.length;
  let next = off + 1;
  const high = S.canonical.charCodeAt(off);
  const low = S.canonical.charCodeAt(off + 1);
  if (high >= 0xD800 && high <= 0xDBFF && low >= 0xDC00 && low <= 0xDFFF) next++;
  return next;
}
function resizeFromKeyboard(grip, key, amount){
  const mark = grip.closest('rw-highlight');
  const h = mark && S.hls.find(x => x.id === mark.dataset.highlightId);
  if (!h || h.status !== 'attached') return;
  const edge = grip.dataset.edge;
  const block = grip.closest('[data-block-id]');
  const rtl = block && getComputedStyle(block).direction === 'rtl';
  let direction = key === 'ArrowLeft' ? -1 : 1;
  if (rtl) direction *= -1;
  let off = h.position[edge];
  for (let i = 0; i < amount; i++) off = stepCodePoint(off, direction);
  let bounds = resizeBounds(h, edge, off);
  bounds = trimBounds(bounds.start, bounds.end);
  if (bounds.end <= bounds.start ||
      (bounds.start === h.position.start && bounds.end === h.position.end)) return;
  const before = JSON.stringify(S.hls);
  refreshAnchors(h, bounds.start, bounds.end, {
    strategy: 'resized', confidence: 1, touchUpdatedAt: true
  });
  const merged = commit(h, before);
  requestAnimationFrame(() => {
    focusGrip(merged.id, edge);
    showTools(merged.id);
  });
}
function paintFocus(){
  $$('[data-block-id].focused').forEach(el => el.classList.remove('focused'));
  const b = S.blocks[S.focus]; if (!b) return;
  b.el.classList.add('focused');
  b.el.scrollIntoView({ block:'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}

/* ============================================================
   8. toolbar + note popover
   ============================================================ */
function anchorRectOf(id){
  const els = $$(`rw-highlight[data-highlight-id="${id}"]`);
  if (!els.length) return null;
  const last = els[els.length - 1];
  const wrap = $('.reader').getBoundingClientRect();
  const r = last.getBoundingClientRect();
  return { top: r.bottom - wrap.top + 8, left: Math.max(0, r.left - wrap.left) };
}
function showTools(id){
  const pos = anchorRectOf(id); const t = $('#tools');
  if (!pos) return hideTools();
  t.style.top = pos.top + 'px'; t.style.left = pos.left + 'px';
  t.classList.add('show'); t.dataset.id = id;
}
function hideTools(){ $('#tools').classList.remove('show'); }
$('#tools').addEventListener('click', e => {
  const act = e.target.dataset.act; const id = $('#tools').dataset.id;
  if (!act || !id) return;
  const h = S.hls.find(x => x.id === id); if (!h) return;
  if (act === 'note') openPop(id, 'note');
  if (act === 'tag') openPop(id, 'tag');
  if (act === 'copy'){ navigator.clipboard?.writeText(h.quote.exact); toast('Quote copied'); hideTools(); }
  if (act === 'delete'){ pushUndo(); S.hls = S.hls.filter(x => x.id !== id); S.active = null; save(); repaint(); hideTools(); }
});
function openPop(id, focusField){
  const h = S.hls.find(x => x.id === id); if (!h) return;
  const pos = anchorRectOf(id) || { top: 40, left: 0 };
  const p = $('#pop');
  p.style.top = pos.top + 'px'; p.style.left = pos.left + 'px';
  p.dataset.id = id; p.classList.add('show'); hideTools();
  $('#popNote').value = h.note || '';
  $('#popTags').value = (h.tags || []).join(', ');
  (focusField === 'tag' ? $('#popTags') : $('#popNote')).focus();
}
function closePop(){ $('#pop').classList.remove('show'); }
$('#popCancel').onclick = closePop;
$('#popSave').onclick = () => {
  const h = S.hls.find(x => x.id === $('#pop').dataset.id); if (!h) return;
  pushUndo();
  h.note = $('#popNote').value.trim();
  h.tags = $('#popTags').value.split(',').map(s => s.trim()).filter(Boolean);
  h.updatedAt = new Date().toISOString();
  save(); closePop(); repaint();
};
$('#pop').addEventListener('keydown', e => {
  if (e.key === 'Escape') closePop();
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) $('#popSave').click();
});

/* ============================================================
   9. reattachment — the actual hard part
   Runs when the stored revision no longer matches what we render.
   Rule: a missing overlay is recoverable, a confidently wrong one is not.
   ============================================================ */
function bigrams(s){
  const m = new Map();
  for (let i = 0; i < s.length - 1; i++){ const g = s.slice(i, i+2); m.set(g, (m.get(g)||0)+1); }
  return m;
}
function dice(a, b){
  if (!a.size || !b.size) return 0;
  let hit = 0, total = 0;
  for (const [g,c] of a){ total += c; hit += Math.min(c, b.get(g) || 0); }
  let tb = 0; for (const [,c] of b) tb += c;
  return (2 * hit) / (total + tb);
}
function allIndexOf(hay, needle){
  const out = []; let i = hay.indexOf(needle);
  while (i !== -1 && out.length < 200){ out.push(i); i = hay.indexOf(needle, i + 1); }
  return out;
}
function contextScore(start, end, h){
  const pre = S.canonical.slice(Math.max(0, start - CTX), start);
  const suf = S.canonical.slice(end, end + CTX);
  const tail = (a, b) => { let n = 0; while (n < Math.min(a.length, b.length) && a[a.length-1-n] === b[b.length-1-n]) n++; return n; };
  const head = (a, b) => { let n = 0; while (n < Math.min(a.length, b.length) && a[n] === b[n]) n++; return n; };
  const p = h.quote.prefix ? tail(pre, h.quote.prefix) / Math.max(1, h.quote.prefix.length) : .5;
  const s = h.quote.suffix ? head(suf, h.quote.suffix) / Math.max(1, h.quote.suffix.length) : .5;
  const drift = Math.abs(start - h.position.start) / Math.max(500, S.canonical.length);
  return .55 + .22 * p + .22 * s - Math.min(.18, drift);
}
function resolve(h, opts = {}){
  const q = h.quote.exact;
  const ignorePos = !!opts.forceSearch;

  // 1. same revision: stored offsets are gospel
  if (!ignorePos && h.revisionHash === S.doc.revisionHash && S.canonical.slice(h.position.start, h.position.end) === q)
    return { start: h.position.start, end: h.position.end, confidence: 1, strategy: 'revision' };

  // 2. block id + local offset
  if (!ignorePos){
    const b = S.blocks.find(x => x.id === h.range.startBlockId);
    if (b){
      const s = b.start + h.range.startOffset, e = s + q.length;
      if (S.canonical.slice(s, e) === q) return { start:s, end:e, confidence:.97, strategy:'block' };
    }
    // 3. global offsets
    if (S.canonical.slice(h.position.start, h.position.end) === q)
      return { start:h.position.start, end:h.position.end, confidence:.95, strategy:'position' };
  }

  // 4. exact quote search, ranked by surrounding context
  const hits = allIndexOf(S.canonical, q);
  if (hits.length){
    const scored = hits.map(i => ({ start:i, end:i + q.length, confidence: contextScore(i, i + q.length, h), strategy:'quote' }))
                       .sort((a,b) => b.confidence - a.confidence);
    const [best, next] = scored;
    if (hits.length === 1 || best.confidence - (next ? next.confidence : 0) >= .05) return best;
  }

  // 5. fuzzy window
  if (q.length >= 12 && S.canonical.length < 400000){
    const target = bigrams(q), L = q.length, step = Math.max(1, Math.floor(L / 6));
    let best = null, second = 0;
    for (let i = 0; i + L <= S.canonical.length; i += step){
      const sc = dice(bigrams(S.canonical.slice(i, i + L)), target);
      if (!best || sc > best.confidence){ second = best ? best.confidence : 0; best = { start:i, end:i+L, confidence:sc, strategy:'fuzzy' }; }
      else if (sc > second) second = sc;
    }
    if (best && best.confidence >= .82 && best.confidence - second >= .04) return best;
  }

  // 6. refuse
  return null;
}
function reanchorAll(opts){
  let placed = 0, dropped = 0;
  for (const h of S.hls){
    const r = resolve(h, opts);
    if (r){
      h.position = { start:r.start, end:r.end };
      const sb = blockAt(r.start), eb = blockAt(r.end);
      h.range = { startBlockId: sb.id, startOffset: r.start - sb.start, endBlockId: eb.id, endOffset: r.end - eb.start };
      h.status = 'attached'; h.strategy = r.strategy; h.confidence = Math.round(r.confidence * 100) / 100;
      h.revisionHash = S.doc.revisionHash;
      placed++;
    } else { h.status = 'unplaced'; h.strategy = 'none'; h.confidence = 0; dropped++; }
  }
  return { placed, dropped };
}

/* ============================================================
   10. notebook
   ============================================================ */
function renderNotebook(){
  const nb = $('#nb');
  $('#nbCount').textContent = S.hls.length;
  if (!S.hls.length){
    nb.innerHTML = `<div class="empty">No highlights yet.<br><br>Drag across any sentence, or press <b>↓</b> then <b>H</b> to mark a whole paragraph.</div>`;
    return;
  }
  const sorted = [...S.hls].sort((a,b) => (a.status === b.status ? a.position.start - b.position.start : a.status === 'attached' ? -1 : 1));
  nb.innerHTML = sorted.map(h => `
    <button type="button" class="card ${h.id === S.active ? 'sel' : ''}" data-id="${h.id}" aria-pressed="${h.id === S.active}">
      <div class="q">${esc(h.quote.exact)}</div>
      ${h.note ? `<div class="n">${esc(h.note)}</div>` : ''}
      <div class="meta">
        ${(h.tags||[]).map(t => `<span class="tag">${esc(t)}</span>`).join('')}
        ${h.status === 'unplaced' ? '<span class="flag">unplaced</span>' : ''}
        <span class="strat">${h.strategy}${h.confidence != null && h.strategy !== 'created' ? ' ' + h.confidence : ''}</span>
      </div>
    </button>`).join('');
}
$('#nb').addEventListener('click', e => {
  const card = e.target.closest('.card'); if (!card) return;
  const h = S.hls.find(x => x.id === card.dataset.id); if (!h) return;
  S.active = h.id; renderNotebook();
  if (h.status !== 'attached') return toast('This one has no confident position in the document');
  markActive(h.id);
  const el = document.querySelector(`rw-highlight[data-highlight-id="${h.id}"]`);
  el?.scrollIntoView({ block:'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  setTimeout(() => showTools(h.id), 320);
});

/* ============================================================
   11. export
   ============================================================ */
function toMarkdown(){
  const d = S.doc;
  const body = [...S.hls].sort((a,b) => a.position.start - b.position.start).map(h =>
    `> ${h.quote.exact.replace(/\n/g,'\n> ')}\n` +
    (h.note ? `\n${h.note}\n` : '') +
    ((h.tags||[]).length ? `\n${h.tags.map(t => '#' + t.replace(/\s+/g,'-')).join(' ')}\n` : '') +
    (h.status !== 'attached' ? `\n*(position not recoverable in the current revision)*\n` : '')
  ).join('\n---\n\n');
  return `# ${d.title}\n\n${d.url ? d.url + '\n' : ''}Captured ${new Date(d.capturedAt).toISOString().slice(0,10)} · revision ${d.revisionHash}\n\n${body}\n`;
}
let modalReturnFocus = null;
function showModal(html){
  modalReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  $('#modal').innerHTML = html;
  $('#veil').classList.add('show');
  $('#veil').setAttribute('aria-hidden', 'false');
  $('.bar').inert = true;
  $('.stage').inert = true;
  requestAnimationFrame(() => {
    const heading = $('#modal h3');
    if (heading && !heading.id) heading.id = 'modalTitle';
    if (heading) $('#modal').setAttribute('aria-labelledby', heading.id);
    const first = $('#modal input:not([disabled]), #modal textarea:not([disabled]), #modal button:not([disabled]), #modal a[href]');
    (first || $('#modal')).focus();
  });
}
function closeModal(){
  if (!$('#veil').classList.contains('show')) return;
  $('#veil').classList.remove('show');
  $('#veil').setAttribute('aria-hidden', 'true');
  $('.bar').inert = false;
  $('.stage').inert = false;
  const target = modalReturnFocus;
  modalReturnFocus = null;
  target?.focus?.({ preventScroll:true });
}
$('#veil').addEventListener('click', e => { if (e.target === $('#veil')) closeModal(); });
$('#modal').addEventListener('click', e => {
  if (e.target.closest('[data-modal-close]')) closeModal();
});
document.addEventListener('keydown', e => {
  if (!$('#veil').classList.contains('show')) return;
  if (e.key === 'Escape'){
    e.preventDefault();
    e.stopImmediatePropagation();
    closeModal();
    return;
  }
  if (e.key !== 'Tab') return;
  const focusable = $$(
    '#modal button:not([disabled]), #modal a[href], #modal input:not([disabled]), #modal textarea:not([disabled]), #modal select:not([disabled]), #modal [tabindex]:not([tabindex="-1"])'
  ).filter(element => element.offsetParent !== null);
  if (!focusable.length){
    e.preventDefault();
    $('#modal').focus();
    return;
  }
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first){
    e.preventDefault(); last.focus();
  } else if (!e.shiftKey && document.activeElement === last){
    e.preventDefault(); first.focus();
  }
}, true);

function downloadText(filename, value, type){
  const blob = new Blob([value], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
function safeFilename(value){ return value.replace(/[^\p{L}\p{N}._-]+/gu, '-').replace(/^-|-$/g, '').slice(0, 80) || 'marginal'; }
function openExport(kind){
  if (!S.doc) return toast('Open a document to export it');
  const markdown = kind === 'md';
  const value = markdown
    ? toMarkdown()
    : JSON.stringify({ document: S.doc, highlights: S.hls }, null, 2);
  showModal(`
    <h3>${markdown ? 'Markdown' : 'JSON'}</h3>
    <p>${markdown ? 'The quote, the note, the tags, the source. Portable by default.' : 'The frozen article, every anchor, and every note — the complete local record.'}</p>
    <textarea id="exportValue" readonly>${esc(value)}</textarea>
    <div class="row">
      <button data-modal-close>Close</button>
      <button id="exportDownload">Download</button>
      <button class="primary" id="exportCopy">Copy</button>
    </div>`);
  $('#exportCopy').onclick = async () => {
    try { await navigator.clipboard.writeText(value); toast('Copied'); }
    catch { toast('Clipboard access was refused'); }
  };
  $('#exportDownload').onclick = () => downloadText(
    `${safeFilename(S.doc.title)}.${markdown ? 'md' : 'json'}`,
    value,
    markdown ? 'text/markdown;charset=utf-8' : 'application/json;charset=utf-8'
  );
}
$('#btnMd').onclick = () => openExport('md');
$('#btnJson').onclick = () => openExport('json');

const BACKUP_FORMAT = 'marginal-backup';
const BACKUP_VERSION = 1;

function documentSummary(d){
  return {
    id:d.id, title:d.title, url:d.url, capturedAt:d.capturedAt,
    revisionHash:d.revisionHash, excerpt:d.excerpt || '', siteName:d.siteName || ''
  };
}

async function libraryBackup(){
  const documents = [];
  for (const summary of [...S.docs].sort((a,b) => a.capturedAt.localeCompare(b.capturedAt))){
    const documentRecord = await sget('doc:' + summary.id);
    if (!documentRecord) throw new Error(`"${summary.title}" is missing its frozen document`);
    documents.push({
      document: documentRecord,
      highlights: (await sget('hls:' + summary.id)) || []
    });
  }
  return {
    format: BACKUP_FORMAT,
    version: BACKUP_VERSION,
    exportedAt: new Date().toISOString(),
    documents
  };
}

function backupString(value, label, max){
  if (typeof value !== 'string' || value.length > max) throw new Error(`${label} is invalid`);
  return value;
}
function backupDate(value, label){
  const date = backupString(value, label, 100);
  if (!Number.isFinite(Date.parse(date))) throw new Error(`${label} is invalid`);
  return new Date(date).toISOString();
}
function backupOffset(value, fallback){
  return Number.isSafeInteger(value) && value >= 0 ? value : fallback;
}
function normalizeBackupHighlight(value, docId){
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('A highlight record is invalid');
  const exact = backupString(value.quote?.exact, 'Highlight quote', 1_000_000);
  if (!exact) throw new Error('A highlight has an empty quote');
  const start = backupOffset(value.position?.start, 0);
  const end = Math.max(start, backupOffset(value.position?.end, start + exact.length));
  const status = value.status === 'unplaced' ? 'unplaced' : 'attached';
  return {
    id: backupString(value.id, 'Highlight id', 200),
    docId,
    revisionHash: typeof value.revisionHash === 'string' ? value.revisionHash.slice(0, 200) : '',
    note: typeof value.note === 'string' ? value.note.slice(0, 100_000) : '',
    tags: Array.isArray(value.tags)
      ? value.tags.filter(tag => typeof tag === 'string').slice(0, 100).map(tag => tag.slice(0, 200))
      : [],
    createdAt: Number.isFinite(Date.parse(value.createdAt)) ? new Date(value.createdAt).toISOString() : new Date().toISOString(),
    updatedAt: Number.isFinite(Date.parse(value.updatedAt)) ? new Date(value.updatedAt).toISOString() : new Date().toISOString(),
    status,
    strategy: typeof value.strategy === 'string' ? value.strategy.slice(0, 50) : 'restored',
    confidence: Number.isFinite(value.confidence) ? Math.max(0, Math.min(1, value.confidence)) : 0,
    position: { start, end },
    range: {
      startBlockId: typeof value.range?.startBlockId === 'string' ? value.range.startBlockId.slice(0, 200) : '',
      startOffset: backupOffset(value.range?.startOffset, start),
      endBlockId: typeof value.range?.endBlockId === 'string' ? value.range.endBlockId.slice(0, 200) : '',
      endOffset: backupOffset(value.range?.endOffset, end)
    },
    quote: {
      exact,
      prefix: typeof value.quote?.prefix === 'string' ? value.quote.prefix.slice(-CTX) : '',
      suffix: typeof value.quote?.suffix === 'string' ? value.quote.suffix.slice(0, CTX) : ''
    }
  };
}
function normalizeBackup(raw){
  if (!raw || typeof raw !== 'object' || raw.format !== BACKUP_FORMAT || raw.version !== BACKUP_VERSION){
    throw new Error('This is not a supported Marginal backup');
  }
  if (!Array.isArray(raw.documents) || raw.documents.length > 10_000){
    throw new Error('The backup document list is invalid');
  }
  const seen = new Set();
  return raw.documents.map((record, index) => {
    const value = record?.document;
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`Document ${index + 1} is invalid`);
    const id = backupString(value.id, `Document ${index + 1} id`, 200);
    if (!/^[A-Za-z0-9._-]+$/.test(id) || seen.has(id)) throw new Error(`Document ${index + 1} has an invalid or duplicate id`);
    seen.add(id);
    const html = sanitize(backupString(value.html, `Document ${index + 1} HTML`, 10_000_000));
    const documentRecord = {
      id,
      title: backupString(value.title, `Document ${index + 1} title`, 500).trim() || 'Untitled',
      byline: typeof value.byline === 'string' ? value.byline.slice(0, 500) : '',
      excerpt: typeof value.excerpt === 'string' ? value.excerpt.slice(0, 2_000) : textOfHtml(html).slice(0, 220),
      siteName: typeof value.siteName === 'string' ? value.siteName.slice(0, 500) : '',
      url: safeHttpUrl(typeof value.url === 'string' ? value.url.slice(0, 10_000) : ''),
      capturedAt: backupDate(value.capturedAt, `Document ${index + 1} date`),
      html,
      revisionHash: hash(html)
    };
    const highlights = Array.isArray(record.highlights)
      ? record.highlights.map(highlight => normalizeBackupHighlight(highlight, id))
      : [];
    if (new Set(highlights.map(highlight => highlight.id)).size !== highlights.length){
      throw new Error(`"${documentRecord.title}" has duplicate highlight ids`);
    }
    return { document: documentRecord, highlights };
  });
}
async function restoreBackup(raw){
  const records = normalizeBackup(raw);
  const restoredIds = new Set(records.map(record => record.document.id));
  const merged = S.docs.filter(doc => !restoredIds.has(doc.id));
  merged.push(...records.map(record => documentSummary(record.document)));
  const entries = records.flatMap(record => [
    ['doc:' + record.document.id, record.document],
    ['hls:' + record.document.id, record.highlights]
  ]);
  entries.push(['docs:index', merged]);
  await saveQueue;
  await setValues(entries);
  S.docs = merged;
  renderPicker();
  return records;
}
async function openLibraryBackup(){
  try {
    const backup = await libraryBackup();
    const value = JSON.stringify(backup, null, 2);
    showModal(`
      <h3>Back up the whole library</h3>
      <p>${backup.documents.length} frozen document${backup.documents.length === 1 ? '' : 's'}, with every highlight, anchor, note and tag. Keep this file somewhere outside the browser profile.</p>
      <textarea id="backupValue" readonly aria-label="Complete Marginal backup">${esc(value)}</textarea>
      <div class="row">
        <button data-modal-close>Close</button>
        <button class="primary" id="backupDownload">Download backup</button>
      </div>`);
    $('#backupDownload').onclick = () => downloadText(
      `marginal-backup-${new Date().toISOString().slice(0,10)}.json`,
      value,
      'application/json;charset=utf-8'
    );
  } catch (error){
    toast(error.message || 'The library could not be backed up');
  }
}
function openLibraryRestore(){
  showModal(`
    <h3>Restore a library backup</h3>
    <p>Restoring merges with this library. Documents with matching Marginal ids are replaced only after the entire backup passes validation.</p>
    <div class="field">
      <label for="restoreFile">Backup file</label>
      <input id="restoreFile" type="file" accept="application/json,.json">
    </div>
    <div class="field">
      <label for="restoreValue">Or paste backup JSON</label>
      <textarea id="restoreValue" placeholder='{"format":"marginal-backup",…}'></textarea>
    </div>
    <div class="row">
      <button data-modal-close>Cancel</button>
      <button class="primary" id="restoreLibrary">Validate and restore</button>
    </div>`);
  $('#restoreFile').onchange = async event => {
    const [file] = event.target.files;
    if (!file) return;
    if (file.size > 50_000_000){
      event.target.value = '';
      return toast('That backup is larger than 50 MB');
    }
    try { $('#restoreValue').value = await file.text(); }
    catch { toast('That file could not be read'); }
  };
  $('#restoreLibrary').onclick = async () => {
    const button = $('#restoreLibrary');
    try {
      button.disabled = true;
      button.textContent = 'Validating…';
      const raw = JSON.parse($('#restoreValue').value);
      const records = await restoreBackup(raw);
      closeModal();
      const preferred = records.find(record => record.document.id === S.doc?.id) || records[0];
      if (preferred) await openDoc(preferred.document.id);
      toast(`Restored ${records.length} document${records.length === 1 ? '' : 's'}`);
    } catch (error){
      button.disabled = false;
      button.textContent = 'Validate and restore';
      toast(error instanceof SyntaxError ? 'The backup is not valid JSON' : error.message || 'Restore failed');
    }
  };
}

/* forces every highlight back through search + fuzzy, ignoring stored offsets.
   This is how you find out whether your anchors would survive a re-parse. */
$('#btnAudit').onclick = () => {
  if (!S.hls.length) return toast('Nothing to re-anchor');
  const before = JSON.stringify(S.hls.map(h => h.position));
  const { placed, dropped } = reanchorAll({ forceSearch: true });
  const same = JSON.stringify(S.hls.map(h => h.position)) === before;
  save(); repaint();
  toast(`${placed} re-found from quote alone, ${dropped} refused${same ? ', all landed identically' : ', some moved'}`);
};

/* ============================================================
   12. documents
   ============================================================ */
function save(){
  if (!S.doc) return Promise.resolve();
  const key = 'hls:' + S.doc.id;
  const snapshot = JSON.parse(JSON.stringify(S.hls));
  const operation = saveQueue.then(() => sset(key, snapshot));
  saveQueue = operation.catch(() => {});
  operation.catch(() => toast('This change could not be saved'));
  return operation;
}
async function saveDoc(d){
  const nextDocs = S.docs.filter(x => x.id !== d.id).concat([documentSummary(d)]);
  await setValues([
    ['doc:' + d.id, d],
    ['docs:index', nextDocs]
  ]);
  S.docs = nextDocs;
}
async function openDoc(id){
  const d = await sget('doc:' + id);
  if (!d) return toast('That document could not be loaded');
  S.doc = d;
  document.title = `${d.title} — Marginal`;
  S.hls = (await sget('hls:' + id)) || [];
  S.focus = -1; S.active = null; S.undo = [];
  renderDocument();
  const stale = S.hls.some(h => h.revisionHash !== d.revisionHash);
  const r = reanchorAll();
  repaint();
  if (stale && r.dropped) toast(`${r.dropped} highlight${r.dropped > 1 ? 's' : ''} kept in the Notebook — no confident position`);
  $('#docpick').value = id;
  window.scrollTo(0,0);
}
function renderPicker(){
  const ordered = [...S.docs].sort((a,b) => b.capturedAt.localeCompare(a.capturedAt));
  $('#docpick').innerHTML = ordered.map(d => `<option value="${esc(d.id)}">${esc(d.title)}</option>`).join('');
  $('#docpick').disabled = !ordered.length;
  if (S.doc) $('#docpick').value = S.doc.id;
}
$('#docpick').onchange = e => openDoc(e.target.value);

function openAddDocument(){
  showModal(`
  <h3>Add a document</h3>
  <p>Paste an article. Rich text keeps its structure; plain text is split into paragraphs. Whatever lands here is frozen — the copy you highlight never changes underneath you.</p>
  <div class="field"><label>Title</label><input id="mTitle" placeholder="Untitled"></div>
  <div class="field"><label>Source URL (optional)</label><input id="mUrl" placeholder="https://"></div>
  <div class="field"><label>Content</label><textarea id="mBody" placeholder="Paste here…"></textarea></div>
  <div class="row"><button data-modal-close>Cancel</button><button class="primary" id="freezeDocument">Freeze it</button></div>`);
  $('#freezeDocument').onclick = addDoc;
  $('#mTitle').focus();
}
$('#btnNew').onclick = openAddDocument;

async function addDoc(){
  const title = ($('#mTitle').value.trim() || 'Untitled');
  const rawUrl = $('#mUrl').value.trim();
  const url = rawUrl ? safeHttpUrl(rawUrl) : '';
  if (rawUrl && !url) return toast('Source URL must begin with http:// or https://');
  const raw = $('#mBody').value;
  if (!raw.trim()) return toast('Paste something first');
  const looksHtml = /<\/?(p|div|h[1-6]|ul|ol|li|article|section|span)\b/i.test(raw);
  const html = sanitize(looksHtml ? raw : textToHtml(raw));
  const d = {
    id: uid(), title, url, capturedAt: new Date().toISOString(), html,
    revisionHash: hash(html), excerpt: textOfHtml(html).slice(0, 220), siteName: hostname(url)
  };
  await saveDoc(d); renderPicker(); closeModal();
  await sset('hls:' + d.id, []);
  openDoc(d.id);
}
function textOfHtml(html){
  const template = document.createElement('template');
  template.innerHTML = html;
  return (template.content.textContent || '').replace(/\s+/g, ' ').trim();
}

/* also accept a rich paste straight onto the modal textarea */
document.addEventListener('paste', e => {
  const ta = document.getElementById('mBody');
  if (!ta || document.activeElement !== ta) return;
  const html = e.clipboardData?.getData('text/html');
  if (html){ e.preventDefault(); ta.value = html; toast('Pasted with formatting'); }
});

/* ============================================================
   13. library
   Search includes document metadata, exact quotes, notes and tags.
   ============================================================ */
let libraryRecords = [];
async function loadLibraryRecords(){
  libraryRecords = await Promise.all(
    [...S.docs]
      .sort((a,b) => b.capturedAt.localeCompare(a.capturedAt))
      .map(async doc => ({ doc, highlights: (await sget('hls:' + doc.id)) || [] }))
  );
  return libraryRecords;
}
function libraryHaystack(record){
  return [
    record.doc.title, record.doc.siteName, record.doc.url, record.doc.excerpt,
    ...record.highlights.flatMap(h => [h.quote?.exact, h.note, ...(h.tags || [])])
  ].filter(Boolean).join('\n').toLocaleLowerCase();
}
function matchingExcerpt(record, query){
  if (query){
    const hit = record.highlights.find(h =>
      [h.quote?.exact, h.note, ...(h.tags || [])]
        .filter(Boolean).join(' ').toLocaleLowerCase().includes(query)
    );
    if (hit) return hit.quote?.exact || hit.note;
  }
  return record.doc.excerpt || record.highlights[0]?.quote?.exact || 'No highlights yet.';
}
function renderLibrary(query = ''){
  const normalized = query.trim().toLocaleLowerCase();
  const matches = libraryRecords.filter(record =>
    !normalized || libraryHaystack(record).includes(normalized)
  );
  const list = $('#libraryList');
  if (!list) return;
  list.innerHTML = matches.length ? matches.map(record => {
    const { doc, highlights } = record;
    const source = doc.siteName || hostname(doc.url) || 'pasted';
    return `
      <article class="library-item ${S.doc?.id === doc.id ? 'current' : ''}" data-doc-id="${esc(doc.id)}">
        <div>
          <div class="library-title">${esc(doc.title)}</div>
          <div class="library-excerpt">${esc(matchingExcerpt(record, normalized))}</div>
          <div class="library-meta">
            <span>${esc(source)}</span>
            <span>${new Date(doc.capturedAt).toLocaleDateString()}</span>
            <span>${highlights.length} highlight${highlights.length === 1 ? '' : 's'}</span>
          </div>
        </div>
        <div class="library-actions">
          <button data-open-doc>Read</button>
          ${doc.url ? `<a href="${esc(doc.url)}" target="_blank" rel="noopener noreferrer">Original</a>` : ''}
          <button class="delete" data-delete-doc>Delete</button>
        </div>
      </article>`;
  }).join('') : `
    <div class="library-empty">
      ${S.docs.length ? 'No documents or highlights match this search.' : 'Your library is empty. Capture a page with the Marginal toolbar button, or paste a document.'}
    </div>`;
}
async function openLibrary(){
  showModal(`
    <div class="library-head">
      <div class="copy">
        <h3>Library</h3>
        <p>Search titles, sources, exact quotes, notes and tags across every frozen document.</p>
      </div>
      <div class="head-actions">
        <button id="libraryBackup">Backup</button>
        <button id="libraryRestore">Restore</button>
        <button data-modal-close aria-label="Close library">Close</button>
      </div>
    </div>
    <div class="library-search"><input id="libraryQuery" type="search" placeholder="Search the words you kept…" autocomplete="off"></div>
    <div class="library-list" id="libraryList"><div class="library-empty">Loading local library…</div></div>
    ${S.docs.length ? '' : '<div class="row"><button class="primary" id="libraryAdd">Add document</button></div>'}
  `);
  const query = $('#libraryQuery');
  query.oninput = e => renderLibrary(e.target.value);
  query.focus();
  $('#libraryBackup').onclick = openLibraryBackup;
  $('#libraryRestore').onclick = openLibraryRestore;
  try {
    await loadLibraryRecords();
    if (!$('#libraryList')) return;
    renderLibrary(query.value);
    $('#libraryAdd')?.addEventListener('click', openAddDocument);
  } catch (error){
    if ($('#libraryList')) $('#libraryList').innerHTML = '<div class="library-empty">The local library could not be read. Reload Marginal and try again.</div>';
    console.error('Marginal library read failed', error);
  }
}
async function deleteDocument(id){
  const record = S.docs.find(doc => doc.id === id);
  if (!record) return;
  showModal(`
    <div class="confirm-box">
      <h3>Delete this frozen copy?</h3>
      <p>The article and all of its highlights and notes will be removed from this browser. Export first if you may want them later.</p>
      <div class="confirm-quote">${esc(record.title)}</div>
      <div class="row">
        <button id="cancelDelete">Keep it</button>
        <button class="primary" id="confirmDelete">Delete permanently</button>
      </div>
    </div>`);
  $('#cancelDelete').onclick = openLibrary;
  $('#confirmDelete').onclick = async () => {
    await saveQueue;
    const nextDocs = S.docs.filter(doc => doc.id !== id);
    await updateValues([['docs:index', nextDocs]], ['doc:' + id, 'hls:' + id]);
    S.docs = nextDocs;
    if (S.doc?.id === id){
      S.doc = null; S.hls = []; S.active = null; S.undo = [];
      if (S.docs.length) await openDoc([...S.docs].sort((a,b) => b.capturedAt.localeCompare(a.capturedAt))[0].id);
      else showEmptyReader();
    }
    renderPicker();
    toast('Document deleted');
    openLibrary();
  };
}
function showEmptyReader(){
  document.title = 'Marginal';
  $('#doc').innerHTML = `
    <h1 data-block-id="title">Your library is empty.</h1>
    <div class="docmeta"><span>Capture an article with the toolbar button, or add one by hand.</span></div>
    <p>Marginal keeps frozen copies locally, so the words underneath a highlight cannot drift.</p>`;
  S.canonical = ''; S.index = []; S.blocks = [];
  $('#nb').innerHTML = '<div class="empty">No document is open.</div>';
  $('#nbCount').textContent = '0';
}
$('#btnLibrary').onclick = openLibrary;
$('#btnLibrarySide').onclick = openLibrary;
$('#modal').addEventListener('click', e => {
  const item = e.target.closest('[data-doc-id]');
  if (!item) return;
  if (e.target.closest('[data-open-doc]')){
    closeModal();
    openDoc(item.dataset.docId);
  }
  if (e.target.closest('[data-delete-doc]')) deleteDocument(item.dataset.docId);
});

/* ============================================================
   14. chrome
   ============================================================ */
$('#btnTheme').onclick = async () => {
  document.body.classList.toggle('dark');
  const dark = document.body.classList.contains('dark');
  $('#btnTheme').setAttribute('aria-pressed', String(dark));
  $('#btnTheme').setAttribute('aria-label', dark ? 'Use light theme' : 'Use dark theme');
  await sset('pref:theme', dark ? 'dark' : 'light');
};
$('#btnAuto').onclick = async () => {
  S.auto = !S.auto;
  $('#btnAuto').classList.toggle('on', S.auto);
  $('#btnAuto').setAttribute('aria-pressed', String(S.auto));
  await sset('pref:auto', S.auto);
  toast(S.auto ? 'Selecting text marks it' : 'Selection no longer marks — use H, or the toolbar');
};
$('#btnSide').onclick = () => {
  const open = $('#side').classList.toggle('open');
  $('#btnSide').setAttribute('aria-expanded', String(window.innerWidth > 1000 || open));
};
function layoutChrome(){
  document.documentElement.style.setProperty('--bar-height', `${$('.bar').offsetHeight}px`);
  $('#btnSide').setAttribute('aria-expanded', String(window.innerWidth > 1000 || $('#side').classList.contains('open')));
  layoutMarginNotes();
  if ($('#tools').dataset.id && $('#tools').classList.contains('show')) showTools($('#tools').dataset.id);
}
window.addEventListener('resize', layoutChrome);

/* ============================================================
   15. seed + boot
   ============================================================ */
const SEED_HTML = `
<p>A highlight looks like the simplest feature in a reader. You drag across a sentence, the sentence turns yellow, you move on. The reason it is not simple is that <em>the sentence you dragged across is not a thing the computer has</em>. What the computer has is a tree of nodes, and your gesture lands somewhere inside it.</p>
<h2>The frozen copy</h2>
<p>The decision that does most of the work is refusing to re-derive the document. A page you saved on Tuesday is stored exactly as it rendered on Tuesday. If the publisher rewrites the lede on Wednesday, adds a newsletter box, or ships a new CMS, none of it reaches your copy.</p>
<p>This turns an impossible problem — keep an annotation attached to an arbitrary webpage forever — into a tractable one: keep an annotation attached to a versioned document you control. Everything downstream gets cheaper.</p>
<blockquote>A missing overlay is recoverable. A confidently wrong overlay is not.</blockquote>
<h2>Four anchors, not one</h2>
<p>A robust annotation stores several independent descriptions of the same passage, so that failure of one does not mean loss of the record:</p>
<ul>
  <li>a structural position — this block, this offset inside it;</li>
  <li>a global character range against the canonical text;</li>
  <li>the exact quote itself;</li>
  <li>the text immediately before and after it.</li>
</ul>
<p>The W3C annotation model calls the last two a <a href="https://www.w3.org/TR/annotation-model/">TextQuoteSelector</a>, and Hypothesis has written at length about resolving them with fuzzy matching when the cheap paths fail. Reader has never published its schema, but its observable behaviour is consistent with roughly this.</p>
<h2>Where it gets loud</h2>
<p>Anchoring is the interesting half of the problem; boundaries are the exhausting half. Consider what the following demand of a selection model:</p>
<table>
  <thead><tr><th>Case</th><th>What breaks</th></tr></thead>
  <tbody>
    <tr><td>Nested emphasis and links</td><td>One logical highlight, several visual fragments</td></tr>
    <tr><td>Repeated identical sentences</td><td>Quote search finds four candidates, all equally good</td></tr>
    <tr><td>Non-breaking spaces</td><td>Offsets drift silently by one character per instance</td></tr>
    <tr><td>Emoji and CJK — 中文的字符 — 🙂</td><td>Length in code units is not length in characters</td></tr>
  </tbody>
</table>
<p>Anchoring is the interesting half of the problem; boundaries are the exhausting half.</p>
<h2>Rendering is disposable</h2>
<p>The record is the highlight. The yellow is a projection of the record, rebuilt from scratch whenever anything changes:</p>
<pre><code>render(doc.html)      // original text, always
normalise(textNodes)  // NBSP, NFC — once
index()               // node -> global offsets
paint(highlights)     // wrap, in reverse order
index()               // again, over the painted tree</code></pre>
<p>Rebuilding is not an optimisation problem at this scale, and it buys an invariant worth far more than the milliseconds: removing every wrapper always restores the document to precisely the text that was captured.</p>
`;
async function boot(){
  S.docs = (await sget('docs:index')) || [];
  const theme = await sget('pref:theme');
  if (theme === 'dark'){
    document.body.classList.add('dark');
    $('#btnTheme').setAttribute('aria-pressed', 'true');
    $('#btnTheme').setAttribute('aria-label', 'Use light theme');
  }
  const auto = await sget('pref:auto');
  S.auto = auto === null ? true : auto;
  $('#btnAuto').classList.toggle('on', S.auto);
  $('#btnAuto').setAttribute('aria-pressed', String(S.auto));

  const seeded = await sget('pref:seeded');
  if (!S.docs.length && !seeded){
    const html = sanitize(SEED_HTML);
    const d = {
      id:'seed', title:'What a highlight actually is', url:'',
      capturedAt:new Date().toISOString(), html, revisionHash: hash(html),
      excerpt:textOfHtml(html).slice(0,220), siteName:'Marginal'
    };
    await saveDoc(d); await sset('hls:seed', []); await sset('pref:seeded', true);
  }
  renderPicker();
  const requested = new URLSearchParams(location.search).get('doc');
  const target = S.docs.find(doc => doc.id === requested)
    || [...S.docs].sort((a,b) => b.capturedAt.localeCompare(a.capturedAt))[0];
  if (target) await openDoc(target.id);
  else showEmptyReader();
  layoutChrome();
}
boot().catch(error => {
  console.error('Marginal could not start', error);
  document.title = 'Marginal — storage error';
  $('#doc').innerHTML = `
    <h1 data-block-id="title">Marginal could not open its local library.</h1>
    <div class="docmeta"><span>Your data has not been deleted.</span></div>
    <p>Reload the extension. If the problem continues, check that browser storage is available before making any changes.</p>`;
  $('#nb').innerHTML = '<div class="empty">Local storage is unavailable.</div>';
  toast('Local storage is unavailable');
});
