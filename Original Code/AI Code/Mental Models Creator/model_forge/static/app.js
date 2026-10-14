const $ = (selector, parent = document) => parent.querySelector(selector);
const form = $('#forge-form');
const source = $('#source-content');
const fileInput = $('#source-file');
const message = $('#form-message');
const dialog = $('#model-dialog');
let models = [];

const escapeHTML = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options});
  let body;
  try { body = await response.json(); } catch { throw new Error(`Server returned ${response.status}`); }
  if (!response.ok) throw new Error(body.error || body.reasons?.join('; ') || `Request failed (${response.status})`);
  return body;
}

function setMessage(text = '', error = false) {
  message.hidden = !text;
  message.textContent = text;
  message.classList.toggle('error', error);
}

function sourceMode() {
  const kind = $('input[name="kind"]:checked').value;
  const config = {
    text: ['Source material', 'Paste a paper excerpt, conversation, thesis, or causal argument…', 'State causal relationships plainly for the strongest offline extraction.'],
    file: ['Local file', 'Choose a text, Markdown, PDF, or audio file…', 'PDF needs the pdf extra; audio needs the audio extra and OPENAI_API_KEY.'],
    url: ['Source URL', 'https://example.com/article', 'The local server fetches and extracts visible page text.'],
    news: ['News query', 'e.g. semiconductor supply constraints', 'Fetches a current RSS news digest and runs the model forward.']
  }[kind];
  $('#source-label').textContent = config[0]; source.placeholder = config[1]; $('#source-help').textContent = config[2];
  source.hidden = kind === 'file'; fileInput.hidden = kind !== 'file';
}

document.querySelectorAll('input[name="kind"]').forEach(input => input.addEventListener('change', sourceMode));

function readUpload(file) {
  if (file.size > 25_000_000) throw new Error('File exceeds the 25 MB upload limit.');
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('The selected file could not be read.'));
    reader.onload = () => resolve({filename:file.name, content:String(reader.result).split(',', 2)[1]});
    reader.readAsDataURL(file);
  });
}

form.addEventListener('submit', async event => {
  event.preventDefault(); setMessage();
  const button = $('.primary', form); button.disabled = true; button.querySelector('span').textContent = 'Forging…';
  try {
    const kind = $('input[name="kind"]:checked').value;
    const upload = kind === 'file' ? await readUpload(fileInput.files[0] || (() => { throw new Error('Choose a file first.'); })()) : null;
    const content = upload ? upload.content : source.value.trim();
    if (!content) throw new Error('Add source material before forging.');
    const result = await api('/api/forge', {method:'POST', body:JSON.stringify({kind, content, filename:upload?.filename, name:$('#model-name').value.trim(), domain:$('#transfer-domain').value.trim(), predictions:Number($('#prediction-count').value)})});
    setMessage(`Accepted “${result.model.name}” with ${result.model.predictions.length} predictions and ${result.collisions.length} collision alert(s).`);
    await loadLibrary(); openModel(result.model.id);
  } catch (error) { setMessage(error.message, true); }
  finally { button.disabled = false; button.querySelector('span').textContent = 'Forge model'; }
});

function card(model) {
  const unresolved = model.predictions.filter(item => item.status === 'open').length;
  return `<button class="model-card" data-id="${escapeHTML(model.id)}"><span class="card-top"><span>Rev. ${model.revision}</span><span>${new Date(model.updated_at).toLocaleDateString()}</span></span><h3>${escapeHTML(model.name)}</h3><p>${escapeHTML(model.scope)}</p><span class="metrics"><span class="metric"><b>${model.edges.length}</b><span>Edges</span></span><span class="metric"><b>${unresolved}</b><span>Open bets</span></span><span class="metric"><b>${Math.round(model.confidence*100)}%</b><span>Earned</span></span></span></button>`;
}

async function loadLibrary() {
  const library = $('#library');
  library.innerHTML = '<div class="empty-state"><p>Reading the model records…</p></div>';
  try {
    models = await api('/api/models');
    library.innerHTML = models.length ? models.map(card).join('') : '<div class="empty-state"><p>No models yet. Feed the forge its first causal argument.</p></div>';
  } catch (error) { library.innerHTML = `<div class="empty-state"><p>${escapeHTML(error.message)}</p></div>`; }
}

async function openModel(id) {
  const model = models.find(item => item.id === id); if (!model) return;
  dialog.dataset.modelId = id;
  const names = Object.fromEntries(model.entities.map(entity => [entity.namespace, entity.name]));
  let collisions = []; try { collisions = await api(`/api/models/${id}/collisions`); } catch {}
  $('#model-detail').innerHTML = `<header class="detail-header"><p class="eyebrow">Typed model / Revision ${model.revision}</p><h2>${escapeHTML(model.name)}</h2><p>${escapeHTML(model.scope)}</p></header><div id="action-message" class="message" hidden></div><div class="detail-metrics"><span class="metric"><b>${Math.round(model.confidence*100)}%</b><span>Earned confidence</span></span><span class="metric"><b>${model.entities.length}</b><span>Entities</span></span><span class="metric"><b>${model.edges.length}</b><span>Causal edges</span></span><span class="metric"><b>${collisions.length}</b><span>Collisions</span></span></div><section class="detail-section"><h3>Compression</h3><p><span class="tag">15 words</span> ${escapeHTML(model.compressions['15'] || 'Not run')}</p><p><span class="tag">40 words</span> ${escapeHTML(model.compressions['40'] || 'Not run')}</p></section><section class="detail-section"><h3>Causal structure</h3>${model.edges.map(edge => `<div class="edge"><span>${escapeHTML(names[edge.cause] || edge.cause)}</span><b>${edge.sign === 'negative' ? '−→' : edge.sign === 'positive' ? '+→' : '?→'}</b><span>${escapeHTML(names[edge.effect] || edge.effect)} <small class="tag">${escapeHTML(edge.support)}</small> <button class="mini-action" data-action="harden" data-edge="${edge.id}">${edge.hardening.length ? 'Harden again' : 'Steelman edge'}</button></span></div>`).join('') || '<p>No edges extracted.</p>'}</section><section class="detail-section"><h3>Falsifiable predictions</h3>${model.predictions.map(p => `<article class="prediction"><p>${escapeHTML(p.statement)}</p><small>Due ${escapeHTML(p.due_date)} · ${Math.round(p.confidence*100)}% confidence · ${escapeHTML(p.status)} · ${p.evaluations.length} live evaluation(s)</small>${p.status === 'open' ? `<div class="score-actions"><button data-action="score" data-prediction="${p.id}" data-outcome="1">Resolve true</button><button data-action="score" data-prediction="${p.id}" data-outcome="0">Resolve false</button></div>` : ''}</article>`).join('')}</section><section class="detail-section"><h3>Run forward on live news</h3><div class="inline-action"><input id="news-query" aria-label="News query" placeholder="News query relevant to this model"><button data-action="news">Run Mirfish</button></div></section><section class="detail-section"><h3>Collision alerts</h3>${collisions.map(c => `<p class="collision">${escapeHTML(c.severity)}: ${escapeHTML(c.reason)}</p>`).join('') || '<p>No contradictory causal signs in the current library.</p>'}</section><section class="detail-section"><h3>First-break anomalies</h3>${model.anomalies.map(a => `<p>— ${escapeHTML(a)}</p>`).join('')}</section>`;
  if (!dialog.open) dialog.showModal();
}

$('#model-detail').addEventListener('click', async event => {
  const button = event.target.closest('[data-action]'); if (!button) return;
  const model = models.find(item => item.id === dialog.dataset.modelId); if (!model) return;
  const action = button.dataset.action; button.disabled = true;
  try {
    let result;
    if (action === 'harden') result = await api(`/api/models/${model.id}/harden`, {method:'POST', body:JSON.stringify({edge_id:button.dataset.edge})});
    if (action === 'score') result = await api(`/api/models/${model.id}/score`, {method:'POST', body:JSON.stringify({prediction_id:button.dataset.prediction, outcome:Number(button.dataset.outcome), note:'Resolved in Model Forge workspace'})});
    if (action === 'news') {
      const query = $('#news-query').value.trim(); if (!query) throw new Error('Enter a live-news query.');
      result = await api(`/api/models/${model.id}/run-news`, {method:'POST', body:JSON.stringify({query})});
    }
    await loadLibrary(); await openModel(model.id);
    const box = $('#action-message'); box.hidden = false;
    box.textContent = action === 'harden' ? `Edge hardened: ${result.payload.verdict}.` : action === 'score' ? 'Prediction resolved; earned confidence recalculated.' : `${result.payload.triggered_prediction_ids.length} prediction signal(s) found.`;
  } catch (error) { const box = $('#action-message'); box.hidden = false; box.className = 'message error'; box.textContent = error.message; }
  finally { button.disabled = false; }
});

$('#library').addEventListener('click', event => { const button = event.target.closest('[data-id]'); if (button) openModel(button.dataset.id); });
$('.dialog-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
$('#refresh').addEventListener('click', loadLibrary);
loadLibrary();
