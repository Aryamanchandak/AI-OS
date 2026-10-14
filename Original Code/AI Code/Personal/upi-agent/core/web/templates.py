"""HTML templates for /tax pages. Inline strings to match dashboard.py style."""

# ---------------------------------------------------------------------------
# Triage queue page
# ---------------------------------------------------------------------------
TRIAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Classify · UPI Agent</title>
<style>
  :root {
    --bg: #0f1115;
    --panel: #1a1d24;
    --panel-2: #252932;
    --border: #2c313c;
    --text: #e6e8eb;
    --muted: #8b929e;
    --accent: #5c9eff;
    --accent-soft: rgba(92,158,255,.12);
    --good: #5cd687;
    --warn: #ffb86b;
    --bad: #ff6b6b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5;
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 24px; border-bottom: 1px solid var(--border);
    background: var(--panel);
  }
  header h1 { margin: 0; font-size: 18px; font-weight: 600; }
  header a { color: var(--accent); text-decoration: none; }
  header a:hover { text-decoration: underline; }
  .nav { display: flex; gap: 16px; align-items: center; }
  .modeToggle {
    display: flex; gap: 4px; background: var(--bg); padding: 3px;
    border-radius: 6px; border: 1px solid var(--border);
  }
  .modeToggle label {
    padding: 4px 12px; cursor: pointer; border-radius: 4px;
    font-size: 13px; color: var(--muted);
  }
  .modeToggle input { display: none; }
  .modeToggle label.active { background: var(--accent-soft); color: var(--accent); }
  .modeToggle label.disabled { opacity: 0.4; cursor: not-allowed; }
  main { max-width: 800px; margin: 24px auto; padding: 0 24px; }
  .upload {
    border: 2px dashed var(--border); border-radius: 8px;
    padding: 24px; text-align: center; margin-bottom: 24px;
    background: var(--panel); cursor: pointer; transition: border-color .15s;
  }
  .upload:hover, .upload.dragover { border-color: var(--accent); }
  .upload input { display: none; }
  .upload .label { color: var(--muted); }
  .upload .stats { margin-top: 12px; color: var(--text); font-size: 13px; }
  .card {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 24px; margin-bottom: 16px;
  }
  .row { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 8px; }
  .row .k { color: var(--muted); }
  .amount { font-size: 24px; font-weight: 600; }
  .amount.debit { color: var(--bad); }
  .amount.credit { color: var(--good); }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; background: var(--panel-2); color: var(--muted);
    margin-left: 6px; text-transform: uppercase; letter-spacing: 0.5px;
  }
  .badge.both { background: rgba(92,214,135,.15); color: var(--good); }
  .context {
    margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border);
  }
  .context h3 { font-size: 12px; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.5px; margin: 12px 0 6px; font-weight: 600; }
  .past, .cal { display: flex; gap: 8px; flex-wrap: wrap; }
  .pill {
    background: var(--panel-2); border: 1px solid var(--border);
    padding: 4px 10px; border-radius: 12px; font-size: 12px;
  }
  .suggestion {
    margin: 16px 0; padding: 12px 16px; background: var(--accent-soft);
    border: 1px solid var(--accent); border-radius: 6px;
  }
  .suggestion .bucket { font-weight: 600; color: var(--accent); }
  .suggestion .reason { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .actions {
    display: flex; gap: 8px; margin-top: 16px; align-items: center;
  }
  select, button {
    background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
    padding: 8px 14px; border-radius: 6px; font-size: 14px; font-family: inherit;
  }
  select { flex: 1; }
  button { cursor: pointer; }
  button.primary { background: var(--accent); color: white; border-color: var(--accent); }
  button.primary:hover { filter: brightness(1.1); }
  button:hover { background: var(--border); }
  .empty {
    text-align: center; padding: 64px 24px; color: var(--muted);
  }
  .empty h2 { color: var(--text); margin-bottom: 8px; }
  .progress { color: var(--muted); font-size: 12px; text-align: center; margin-top: 8px; }
  dialog {
    background: var(--panel); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 24px; max-width: 400px;
  }
  dialog::backdrop { background: rgba(0,0,0,0.6); }
  dialog .dialog-actions { display: flex; gap: 8px; margin-top: 16px; justify-content: flex-end; }
  .toast {
    position: fixed; top: 20px; right: 20px; padding: 12px 20px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
    z-index: 100; opacity: 0; transition: opacity .2s;
  }
  .toast.show { opacity: 1; }
  .toast.error { border-color: var(--bad); }
  .toast.success { border-color: var(--good); }
  .desc { font-size: 12px; color: var(--muted); font-family: monospace;
    word-break: break-all; margin-top: 4px; }
</style>
</head>
<body>
<header>
  <div class="nav">
    <a href="/">← Dashboard</a>
    <h1>Classify</h1>
  </div>
  <div class="nav">
    <div class="modeToggle" id="modeToggle">
      <label data-mode="manual"><input type="radio" name="mode" value="manual">Manual</label>
      <label data-mode="ai"><input type="radio" name="mode" value="ai">AI-assisted</label>
    </div>
    <a href="/tax/settings">Settings</a>
    <a href="/tax/export.xlsx">Export</a>
  </div>
</header>

<main>
  <label class="upload" id="uploadZone">
    <input type="file" id="fileInput" accept=".xls,.xlsx,.tsv,.csv">
    <div class="label">Drop your SBI statement here, or click to browse</div>
    <div class="stats" id="uploadStats"></div>
  </label>

  <div id="triageRoot"></div>
  <div class="progress" id="progress"></div>
</main>

<dialog id="retroDialog">
  <h3 style="margin-top:0">Apply to past transactions?</h3>
  <p id="retroQuestion"></p>
  <div class="dialog-actions">
    <button id="retroNo">Just this one</button>
    <button id="retroYes" class="primary">Apply to all</button>
  </div>
</dialog>

<div class="toast" id="toast"></div>

<script>
'use strict';

let currentPayment = null;
let currentMode = 'manual';

function $(id) { return document.getElementById(id); }
function fmtRupees(n) {
  if (n == null) return '—';
  return '₹' + Number(n).toLocaleString('en-IN', {maximumFractionDigits: 2});
}
function fmtDate(s) {
  if (!s) return '';
  return new Date(s).toLocaleDateString('en-IN', {day:'numeric', month:'short', year:'numeric'});
}
function toast(msg, kind) {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast show ' + (kind || '');
  setTimeout(() => t.className = 'toast', 2500);
}

async function loadSettings() {
  const r = await fetch('/tax/api/settings');
  const s = await r.json();
  currentMode = s.mode || 'manual';
  // Render mode toggle
  document.querySelectorAll('#modeToggle label').forEach(lab => {
    lab.classList.toggle('active', lab.dataset.mode === currentMode);
    if (lab.dataset.mode === 'ai' && !s.llm_endpoint) {
      lab.classList.add('disabled');
      lab.title = 'Configure local LLM endpoint in Settings first';
    }
  });
}

document.querySelectorAll('#modeToggle label').forEach(lab => {
  lab.addEventListener('click', async (e) => {
    if (lab.classList.contains('disabled')) {
      e.preventDefault();
      toast('Configure local LLM endpoint in Settings first', 'error');
      return;
    }
    const newMode = lab.dataset.mode;
    await fetch('/tax/api/settings', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({mode: newMode}),
    });
    currentMode = newMode;
    document.querySelectorAll('#modeToggle label').forEach(
      l => l.classList.toggle('active', l.dataset.mode === newMode));
    if (currentPayment) renderCurrent();
  });
});

// --- Upload ---------------------------------------------------------------
const upload = $('uploadZone');
const fileInput = $('fileInput');
upload.addEventListener('dragover', (e) => {
  e.preventDefault(); upload.classList.add('dragover');
});
upload.addEventListener('dragleave', () => upload.classList.remove('dragover'));
upload.addEventListener('drop', (e) => {
  e.preventDefault(); upload.classList.remove('dragover');
  if (e.dataTransfer.files.length) {
    fileInput.files = e.dataTransfer.files;
    handleUpload();
  }
});
fileInput.addEventListener('change', handleUpload);

async function handleUpload() {
  if (!fileInput.files.length) return;
  const fd = new FormData();
  fd.append('file', fileInput.files[0]);
  $('uploadStats').textContent = 'Parsing...';
  try {
    const r = await fetch('/tax/upload', {method:'POST', body: fd});
    if (!r.ok) {
      const err = await r.text();
      throw new Error(err);
    }
    const stats = await r.json();
    $('uploadStats').innerHTML =
      `Parsed <b>${stats.parsed}</b> · ` +
      `New <b>${stats.inserted}</b> · ` +
      `Already had <b>${stats.matched_existing}</b> · ` +
      `Auto-classified <b>${stats.auto_classified}</b>`;
    fileInput.value = '';
    loadNext();
  } catch (e) {
    $('uploadStats').textContent = 'Error: ' + e.message;
    toast('Upload failed', 'error');
  }
}

// --- Triage queue --------------------------------------------------------
async function loadNext() {
  const r = await fetch('/tax/api/queue?limit=1');
  const items = await r.json();
  if (!items.length) {
    $('triageRoot').innerHTML = '<div class="empty"><h2>All caught up</h2>' +
      '<p>No transactions waiting for classification.</p></div>';
    $('progress').textContent = '';
    currentPayment = null;
    return;
  }
  const ctxR = await fetch('/tax/api/payment/' + items[0].id + '/context');
  currentPayment = await ctxR.json();
  renderCurrent();
}

function renderCurrent() {
  if (!currentPayment) return;
  const c = currentPayment;
  const p = c.payment;
  const sourceBadge = p.source === 'both'
    ? '<span class="badge both" title="Confirmed via SMS and Excel">verified</span>'
    : p.source === 'excel'
      ? '<span class="badge">excel</span>'
      : p.source === 'sms' ? '<span class="badge">sms</span>' : '';

  const showSugg = currentMode === 'ai' && c.suggestion.bucket;
  const suggHtml = showSugg ? `
    <div class="suggestion">
      Suggested: <span class="bucket">${c.suggestion.bucket}</span>
      <div class="reason">${c.suggestion.reason}
        · ${(c.suggestion.confidence*100).toFixed(0)}% confidence</div>
    </div>` : '';

  const pastHtml = c.past_classifications.length
    ? `<h3>Same merchant before</h3><div class="past">${
        c.past_classifications.map(x => `<span class="pill">${x.category} (${x.n})</span>`).join('')
      }</div>` : '';

  const calHtml = (c.calendar_events && c.calendar_events.length)
    ? `<h3>Calendar that day</h3><div class="cal">${
        c.calendar_events.map(e => `<span class="pill">${e.title || ''}</span>`).join('')
      }</div>` : '';

  const bucketOptions = c.buckets.length
    ? c.buckets.map(b => `<option value="${b}"${b===c.suggestion.bucket?' selected':''}>${b}</option>`).join('')
    : '<option value="" disabled>No buckets — go to Settings</option>';

  $('triageRoot').innerHTML = `
    <div class="card">
      <div class="row">
        <div>
          <div class="amount ${p.direction}">
            ${p.direction === 'debit' ? '−' : '+'}${fmtRupees(p.amount)}
          </div>
          <div class="row" style="margin-top:6px">
            <span class="k">${fmtDate(p.occurred_at)}</span>
            <span><span class="badge">${p.txn_kind || 'upi'}</span>${sourceBadge}</span>
          </div>
        </div>
      </div>
      <div class="row" style="margin-top:16px">
        <span class="k">Counterparty</span>
        <span>${p.counterparty_name || '<i>—</i>'}</span>
      </div>
      ${p.counterparty_vpa ? `<div class="row"><span class="k">VPA</span><span>${p.counterparty_vpa}</span></div>` : ''}
      ${p.narration ? `<div class="row"><span class="k">Note</span><span>${p.narration}</span></div>` : ''}
      ${p.raw_text ? `<div class="desc">${p.raw_text}</div>` : ''}

      <div class="context">
        ${pastHtml}
        ${calHtml}
        ${suggHtml}
        <div class="actions">
          <select id="bucketSelect">
            <option value="">— choose bucket —</option>
            ${bucketOptions}
          </select>
          <button id="confirmBtn" class="primary">Confirm</button>
          <button id="skipBtn">Skip</button>
        </div>
      </div>
    </div>`;

  $('confirmBtn').addEventListener('click', onConfirm);
  $('skipBtn').addEventListener('click', loadNext);
  $('progress').textContent = `${c.queue_remaining} transaction${c.queue_remaining===1?'':'s'} remaining`;
}

async function onConfirm() {
  const bucket = $('bucketSelect').value;
  if (!bucket) {
    toast('Pick a bucket first', 'error');
    return;
  }
  const c = currentPayment;
  // If there are unclassified same-merchant rows, ask about retro
  if (c.retro_unclassified_count > 0) {
    $('retroQuestion').innerHTML =
      `Apply <b>${bucket}</b> to <b>${c.retro_unclassified_count}</b> ` +
      `other unclassified ${c.payment.counterparty_name || c.payment.counterparty_vpa || 'merchant'} txn` +
      (c.retro_unclassified_count===1?'':'s') + '?';
    const dlg = $('retroDialog');
    dlg.showModal();
    $('retroYes').onclick = async () => { dlg.close(); await doClassify(bucket, true); };
    $('retroNo').onclick = async () => { dlg.close(); await doClassify(bucket, false); };
  } else {
    await doClassify(bucket, false);
  }
}

async function doClassify(bucket, applyRetro) {
  try {
    const r = await fetch('/tax/api/payment/' + currentPayment.payment.id + '/classify', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({bucket: bucket, apply_retro: applyRetro}),
    });
    if (!r.ok) throw new Error(await r.text());
    const result = await r.json();
    if (result.retro_applied > 0) {
      toast(`Classified + applied to ${result.retro_applied} more`, 'success');
    } else {
      toast('Classified', 'success');
    }
    loadNext();
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

(async function init() {
  await loadSettings();
  await loadNext();
})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------
SETTINGS_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Settings · UPI Agent</title>
<style>
  :root {
    --bg: #0f1115; --panel: #1a1d24; --panel-2: #252932;
    --border: #2c313c; --text: #e6e8eb; --muted: #8b929e;
    --accent: #5c9eff; --good: #5cd687; --bad: #ff6b6b;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5; }
  header { display: flex; align-items: center; justify-content: space-between;
           padding: 16px 24px; border-bottom: 1px solid var(--border); background: var(--panel); }
  header h1 { margin: 0; font-size: 18px; font-weight: 600; }
  header a { color: var(--accent); text-decoration: none; }
  main { max-width: 720px; margin: 24px auto; padding: 0 24px; }
  section { background: var(--panel); border: 1px solid var(--border);
            border-radius: 8px; padding: 20px 24px; margin-bottom: 16px; }
  section h2 { margin: 0 0 16px; font-size: 15px; font-weight: 600; color: var(--text); }
  .bucketRow { display: flex; gap: 8px; align-items: center; padding: 8px 0;
               border-bottom: 1px solid var(--border); }
  .bucketRow:last-child { border-bottom: none; }
  .bucketRow input.name { flex: 1; background: transparent; border: 1px solid transparent;
                          color: var(--text); padding: 4px 8px; border-radius: 4px;
                          font-size: 14px; font-family: inherit; }
  .bucketRow input.name:focus, .bucketRow input.name:hover {
    border-color: var(--border); background: var(--bg); outline: none;
  }
  .bucketRow.archived { opacity: 0.5; }
  .addRow { display: flex; gap: 8px; margin-top: 12px; }
  .addRow input { flex: 1; }
  input, button {
    background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
    padding: 8px 12px; border-radius: 6px; font-size: 14px; font-family: inherit;
  }
  button { cursor: pointer; }
  button:hover { background: var(--border); }
  button.primary { background: var(--accent); color: white; border-color: var(--accent); }
  button.danger { color: var(--bad); }
  button.icon { padding: 4px 8px; background: transparent; border: none; color: var(--muted); }
  button.icon:hover { color: var(--text); }
  label { display: block; margin-bottom: 4px; color: var(--muted); font-size: 12px;
          text-transform: uppercase; letter-spacing: 0.5px; }
  .field { margin-bottom: 16px; }
  .field input { width: 100%; }
  .row { display: flex; gap: 12px; align-items: center; margin-top: 12px; }
  .testResult { font-size: 13px; margin-top: 8px; }
  .testResult.ok { color: var(--good); }
  .testResult.fail { color: var(--bad); }
  .note { background: rgba(92,158,255,0.08); border-left: 3px solid var(--accent);
          padding: 12px 16px; border-radius: 4px; font-size: 13px; color: var(--muted); }
  .note b { color: var(--text); }
  .toast { position: fixed; top: 20px; right: 20px; padding: 12px 20px;
           background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
           opacity: 0; transition: opacity .2s; z-index: 100; }
  .toast.show { opacity: 1; }
  .toast.error { border-color: var(--bad); }
  .toast.success { border-color: var(--good); }
</style>
</head>
<body>
<header>
  <div><a href="/">← Dashboard</a> &nbsp;·&nbsp; <a href="/tax">Classify</a></div>
  <h1>Settings</h1>
  <span></span>
</header>

<main>
  <section>
    <h2>Buckets</h2>
    <div id="bucketList"></div>
    <div class="addRow">
      <input type="text" id="newBucket" placeholder="New bucket (e.g. food, transport, rent)">
      <button class="primary" id="addBtn">Add</button>
    </div>
  </section>

  <section>
    <h2>Classification mode</h2>
    <div class="row">
      <label style="margin:0"><input type="radio" name="mode" value="manual"> Manual — I pick from the dropdown</label>
    </div>
    <div class="row">
      <label style="margin:0"><input type="radio" name="mode" value="ai"> AI-assisted — local LLM suggests, I confirm</label>
    </div>
    <div class="field" style="margin-top:16px">
      <label>Local LLM endpoint</label>
      <input type="text" id="llmEndpoint" placeholder="http://127.0.0.1:11434">
    </div>
    <div class="field">
      <label>Model name</label>
      <input type="text" id="llmModel" placeholder="qwen2.5:7b">
    </div>
    <div class="row">
      <button class="primary" id="saveBtn">Save</button>
      <button id="testBtn">Test connection</button>
      <span class="testResult" id="testResult"></span>
    </div>
  </section>

  <section class="note">
    <b>Privacy:</b> Local LLM only. The endpoint URL must be on this machine
    (127.0.0.1) or your local network. Cloud LLMs are never called by this
    system. Compatible with Ollama, llama.cpp server, LM Studio, vLLM —
    anything that exposes an OpenAI-compatible <code>/v1/chat/completions</code>.
  </section>
</main>

<div class="toast" id="toast"></div>

<script>
'use strict';
function $(id){ return document.getElementById(id); }
function toast(msg, kind) {
  const t = $('toast'); t.textContent = msg;
  t.className = 'toast show ' + (kind || '');
  setTimeout(() => t.className = 'toast', 2500);
}

async function loadBuckets() {
  const r = await fetch('/tax/api/buckets');
  const buckets = await r.json();
  const list = $('bucketList');
  if (!buckets.length) {
    list.innerHTML = '<p style="color:var(--muted)">No buckets yet. Add some below.</p>';
    return;
  }
  list.innerHTML = '';
  for (const b of buckets) {
    const archived = !!b.archived_at;
    const row = document.createElement('div');
    row.className = 'bucketRow' + (archived ? ' archived' : '');
    row.innerHTML = `
      <input class="name" value="${b.name}" data-id="${b.id}" data-orig="${b.name}">
      <button class="icon" data-action="${archived ? 'unarchive' : 'archive'}" data-id="${b.id}"
              title="${archived ? 'Restore' : 'Archive'}">
        ${archived ? 'restore' : 'archive'}
      </button>`;
    list.appendChild(row);
  }
  list.querySelectorAll('input.name').forEach(inp => {
    inp.addEventListener('blur', async () => {
      if (inp.value === inp.dataset.orig) return;
      if (!inp.value.trim()) { inp.value = inp.dataset.orig; return; }
      const r = await fetch('/tax/api/buckets/' + inp.dataset.id, {
        method: 'PATCH', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({name: inp.value.trim()})});
      if (r.ok) {
        inp.dataset.orig = inp.value;
        toast('Renamed', 'success');
      } else {
        const err = await r.json().catch(() => ({}));
        toast(err.detail || 'Rename failed', 'error');
        inp.value = inp.dataset.orig;
      }
    });
  });
  list.querySelectorAll('button.icon').forEach(btn => {
    btn.addEventListener('click', async () => {
      const archived = btn.dataset.action === 'archive';
      await fetch('/tax/api/buckets/' + btn.dataset.id, {
        method: 'PATCH', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({archived: archived})});
      toast(archived ? 'Archived' : 'Restored', 'success');
      loadBuckets();
    });
  });
}

$('addBtn').addEventListener('click', async () => {
  const name = $('newBucket').value.trim();
  if (!name) return;
  const r = await fetch('/tax/api/buckets', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name: name})});
  if (r.ok) {
    $('newBucket').value = '';
    toast('Added', 'success');
    loadBuckets();
  } else {
    const err = await r.json().catch(() => ({}));
    toast(err.detail || 'Failed', 'error');
  }
});
$('newBucket').addEventListener('keydown', e => { if (e.key === 'Enter') $('addBtn').click(); });

async function loadSettings() {
  const r = await fetch('/tax/api/settings');
  const s = await r.json();
  document.querySelector(`input[name=mode][value="${s.mode || 'manual'}"]`).checked = true;
  $('llmEndpoint').value = s.llm_endpoint || '';
  $('llmModel').value = s.llm_model || '';
}

$('saveBtn').addEventListener('click', async () => {
  const mode = document.querySelector('input[name=mode]:checked').value;
  const endpoint = $('llmEndpoint').value.trim();
  const model = $('llmModel').value.trim();
  if (mode === 'ai' && !endpoint) {
    toast('Set an LLM endpoint to use AI mode', 'error');
    return;
  }
  const r = await fetch('/tax/api/settings', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({mode, llm_endpoint: endpoint, llm_model: model})});
  if (r.ok) toast('Saved', 'success');
});

$('testBtn').addEventListener('click', async () => {
  const endpoint = $('llmEndpoint').value.trim();
  const result = $('testResult');
  if (!endpoint) {
    result.className = 'testResult fail'; result.textContent = 'Enter an endpoint first';
    return;
  }
  result.className = 'testResult'; result.textContent = 'Testing...';
  const r = await fetch('/tax/api/test_llm', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({endpoint})});
  const data = await r.json();
  if (data.ok) {
    result.className = 'testResult ok';
    result.textContent = data.models.length
      ? `OK — ${data.models.length} model${data.models.length===1?'':'s'} available`
      : 'OK (no models listed)';
  } else {
    result.className = 'testResult fail';
    result.textContent = 'Failed: ' + data.error;
  }
});

loadBuckets();
loadSettings();
</script>
</body>
</html>"""
