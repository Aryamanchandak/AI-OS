/* Keep untrusted source text in textContent, never in HTML or executable attributes. */
const $ = (selector) => document.querySelector(selector);
const labels = { finding: 'Finding', pending: 'Needs your input', ignored: 'Set aside', failed: 'Failed check' };
const titles = { all: 'Your attention queue', finding: 'Worth your attention', pending: 'Waiting on your judgment', ignored: 'Quietly set aside', failed: 'Checks that need attention' };
let data = null;
let view = 'all';
let checking = false;

function node(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text;
  return element;
}
function date(value) {
  return value ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value)) : 'Never';
}
function sourceLink(url, label = url) {
  const link = node('a', '', label);
  if (new URL(url).protocol === 'https:') link.href = url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
}
function message(text, error = false) {
  $('#feedback').textContent = text;
  $('#feedback').className = error ? 'banner error' : 'banner';
  $('#feedback').hidden = false;
}
async function api(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', signal: controller.signal,
      headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-Watchlist-Token': data.token },
      body: body === undefined ? undefined : JSON.stringify(body) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The local server could not complete that request.');
    return result;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The check is taking longer than expected. Refresh shortly to see its recorded result.');
    if (error instanceof TypeError) throw new Error('Could not reach your local watchlist. Make sure the dashboard server is running, then refresh.');
    throw error;
  } finally { clearTimeout(timer); }
}
async function load() {
  $('#refresh-button').disabled = true;
  $('#feed').setAttribute('aria-busy', 'true');
  try {
    data = await api('/api/state');
    render();
    return true;
  } catch (error) {
    message(error.message, true);
    if (!data) $('#feed').replaceChildren(node('div', 'empty', 'Your watch could not be loaded. Use Refresh to try again.'));
    return false;
  } finally {
    $('#refresh-button').disabled = false;
    $('#feed').setAttribute('aria-busy', 'false');
  }
}
function render() {
  $('#watch-name').textContent = data.watch.name;
  $('#watch-question').textContent = data.watch.question;
  $('#demo-banner').hidden = !data.simulated;
  $('#check-button').disabled = data.simulated || checking;
  $('#check-help').textContent = data.simulated ? 'Demo pages are simulated. Live fetching is disabled.' : 'Checks run when you start them.';
  for (const status of ['finding', 'pending', 'ignored', 'failed']) $(`#count-${status}`).textContent = data.counts[status];
  $('#nav-findings').textContent = data.counts.finding;
  $('#nav-pending').textContent = data.counts.pending;
  $('#nav-failed').textContent = data.counts.failed;
  $('#attempt-total').textContent = `${data.attempts_today} of ${data.watch.max_checks_per_day} used`;
  $('#limit-note').textContent = `One page fetch counts as one check. The daily limit resets at midnight UTC; the ${data.watch.interval_hours}-hour interval still applies.`;
  $('#source-total').textContent = `${data.sources.filter(source => source.health === 'current').length} / ${data.sources.length} current`;
  $('#updated-at').textContent = `Updated ${date(data.generated_at)} · your local time`;
  renderSources();
  renderSettings();
  selectView(view);
}
function renderSources() {
  $('#sources').replaceChildren(...data.sources.map(source => {
    const url = new URL(source.url);
    const row = node('div', 'source');
    const heading = node('div', 'source-title');
    const healthLabels = { current: 'Current', overdue: 'Overdue', never: 'Not checked', failed: 'Failed', running: 'Unfinished' };
    heading.append(sourceLink(source.url, url.hostname.replace('www.', '')), node('span', `health ${source.health === 'current' ? '' : 'problem'}`, healthLabels[source.health]));
    row.append(heading, node('p', 'source-path', url.pathname), node('p', 'source-meta', `Last success: ${date(source.last_success)}`),
      node('p', 'source-meta', `Next eligible: ${date(source.next_check)}`));
    return row;
  }));
}
function selectView(next) {
  view = next;
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    if (button.closest('nav')) {
      if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    } else button.setAttribute('aria-pressed', String(active));
  });
  $('#settings').hidden = view !== 'settings';
  $('.content-grid').hidden = view === 'settings';
  if (!data || view === 'settings') return;
  $('#feed-title').textContent = titles[view];
  const items = view === 'failed' ? data.failures : data.items.filter(item => view === 'all' || item.status === view)
    .sort((a, b) => b.importance - a.importance || b.after_at.localeCompare(a.after_at));
  if (!items.length) {
    const empty = node('div', 'empty');
    const copy = { all: ['Nothing needs your attention yet.', 'Your first captures establish context. Meaningful changes will appear here after the next due check.'],
      finding: ['No findings to review.', 'New statements that match your selected rules will appear here, with evidence from both captures.'],
      pending: ['No questions waiting on you.', 'When a change needs your judgment, the question stays saved until you answer it.'],
      ignored: ['Nothing has been set aside yet.', 'Repeated announcements and unrelated edits will appear here with the reason they were ignored.'],
      failed: ['No failed checks recorded.', 'If a capture or assessment fails, its failure stays visible here.'] }[view];
    const link = node('a', '', 'View source health ↓'); link.href = '#source-health';
    empty.append(node('div', 'empty-mark', '✓'), node('h3', '', copy[0]), node('p', '', copy[1]), link);
    $('#feed').replaceChildren(empty);
  } else {
    $('#feed').replaceChildren(...items.map(item => activity(item, view === 'failed')));
    if (items.length === 100) $('#feed').append(node('p', 'panel-note', 'Showing up to 100 recent records. The downloaded brief includes the full history.'));
  }
}
function itemTitle(item) {
  if (item.status === 'pending') return 'A change needs your judgment';
  if (item.status === 'ignored') return 'A change was set aside';
  return item.reason.startsWith('New watched statement(s): ') ? item.reason.slice(26).replaceAll('stable:', '').replaceAll('preview:', '') : 'A finding worth reviewing';
}
function activity(item, failure = false) {
  const card = node(failure ? 'article' : 'button', 'activity');
  const status = failure ? 'failed' : item.status;
  const top = node('div', 'activity-top');
  top.append(node('span', `tag ${status}`, labels[status]), node('span', '', date(item.after_at || item.started_at)));
  const bottom = node('div', 'activity-bottom');
  bottom.append(node('span', '', new URL(item.url).hostname.replace('www.', '')),
    node('span', '', failure ? `Attempt ${item.id}` : `${['', 'Low', 'Medium', 'High'][item.importance] || 'No'} priority · View evidence ↗`));
  card.append(top, node('h3', '', failure ? 'A check did not finish successfully' : itemTitle(item)),
    node('p', '', failure ? item.error || 'Running or interrupted. A later check will record recovery.' : item.question && item.status === 'pending' ? item.question : item.reason), bottom);
  if (!failure) card.addEventListener('click', () => openItem(item.id));
  return card;
}
function renderSettings() {
  const content = $('#settings-content'); content.replaceChildren();
  for (const [label, value] of [['Check frequency', `At least ${data.watch.interval_hours} hours between attempts per source`],
    ['Daily ceiling', `${data.watch.max_checks_per_day} total page attempts (UTC day)`], ['Page size ceiling', `${(data.watch.max_bytes / 1_000_000).toLocaleString()} MB per page`],
    ['Spending ceiling', '$0 · model calls are disabled'], ['Checking mode', 'Manual · start checks from this dashboard']]) {
    const row = node('div', 'setting-row'); row.append(node('span', '', label), node('strong', '', value)); content.append(row);
  }
  content.append(node('h3', '', 'Selected sources'));
  data.watch.urls.forEach(url => { const paragraph = node('p'); paragraph.append(sourceLink(url)); content.append(paragraph); });
  content.append(node('h3', '', 'What counts as relevant'));
  data.watch.rules.forEach(rule => {
    const box = node('div', 'rule'); box.append(node('strong', '', `${rule.name} · importance ${rule.importance}/3`), node('p', '', rule.interpretation));
    if (rule.question) box.append(node('p', '', `Ask you: ${rule.question}`));
    const details = node('details'); details.append(node('summary', '', 'Exact matching pattern'), node('pre', '', rule.pattern));
    box.append(details); content.append(box);
  });
  content.append(node('p', 'panel-note', 'Matching uses explicit text rules. Edit watch.toml and rules.csv to define another watch, then start it with a separate state folder to preserve the meaning of existing evidence.'));
}
async function openItem(id) {
  const dialog = $('#item-dialog');
  $('#item-content').replaceChildren(node('p', '', 'Loading evidence…'));
  dialog.showModal();
  try { renderItem(await api(`/api/items/${id}`)); }
  catch (error) { $('#item-content').replaceChildren(node('p', 'form-feedback', error.message)); }
}
function renderItem(item) {
  const content = $('#item-content');
  const heading = node('h2', '', itemTitle(item)); heading.id = 'item-title';
  content.replaceChildren(heading, node('p', 'panel-note', `Item ${item.id} · ${labels[item.status]} · importance ${item.importance}/3`), sourceLink(item.url));
  content.append(node('h3', '', 'Why this decision was recorded'), node('p', '', item.reason));
  const evidence = node('div', 'evidence-grid');
  for (const [title, at, text] of [['Previous capture · removed lines', item.before_at, item.removed_text], ['Current capture · added lines', item.after_at, item.added_text]]) {
    const column = node('div'); column.append(node('p', 'evidence-label', `${title}\n${date(at)}`), node('pre', '', text || '(none)')); evidence.append(column);
  }
  content.append(node('h3', '', 'Observed changes'), evidence);
  const full = node('details'); full.append(node('summary', '', 'Read the full before-and-after evidence'));
  full.append(node('h3', '', 'Previous capture'), node('pre', '', item.before_text), node('h3', '', 'Current capture'), node('pre', '', item.after_text)); content.append(full);
  content.append(node('h3', '', 'Interpretation'), node('p', '', item.interpretation || 'No interpretation added.'));
  content.append(node('h3', '', 'Suggested local follow-up'), node('p', '', item.suggestion || 'No follow-up suggested.'));
  if (item.answer) content.append(node('h3', '', `Your answer · ${date(item.answered_at)}`), node('p', '', item.answer));
  if (item.status === 'pending') content.append(answerForm(item));
}
function answerForm(item) {
  const form = node('form', 'answer-form');
  const decisionLabel = node('label', '', 'How should this item be treated?'); decisionLabel.htmlFor = 'answer-decision';
  const select = node('select'); select.id = 'answer-decision';
  for (const [value, label] of [['finding', 'Worth reviewing'], ['ignored', 'Set aside']]) { const option = node('option', '', label); option.value = value; select.append(option); }
  const label = node('label', '', 'Your reasoning'); label.htmlFor = 'answer-text';
  const input = node('textarea'); input.id = 'answer-text'; input.required = true; input.maxLength = 2000; input.placeholder = 'Add the context that settles this question…';
  const save = node('button', 'primary', 'Save answer'); save.type = 'submit';
  const feedback = node('p', 'form-feedback'); feedback.setAttribute('role', 'alert');
  form.append(node('h3', '', 'Your judgment is needed'), node('p', '', item.question), decisionLabel, select, label, input, save, node('p', 'panel-note', 'This completes the saved item. It does not send or create anything elsewhere.'), feedback);
  form.addEventListener('submit', async event => {
    event.preventDefault(); save.disabled = true; save.textContent = 'Saving…'; feedback.textContent = '';
    try {
      await api('/api/answer', { item_id: item.id, decision: select.value, answer: input.value.trim() });
      $('#item-dialog').close(); await load(); message(`Your answer was saved to item ${item.id}. No external action was taken.`);
    } catch (error) { feedback.textContent = error.message; }
    finally { save.disabled = false; save.textContent = 'Save answer'; }
  });
  return form;
}
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => selectView(button.dataset.view)));
$('#close-dialog').addEventListener('click', () => $('#item-dialog').close());
$('#refresh-button').addEventListener('click', () => { $('#feedback').hidden = true; load(); });
$('#check-button').disabled = true;
$('#check-button').addEventListener('click', async () => {
  if (!data || checking) return;
  checking = true; $('#check-button').disabled = true; $('#check-button').textContent = 'Checking selected pages…';
  $('#feedback').hidden = true;
  try {
    const result = await api('/api/check', {}); await load();
    const failed = result.results.some(item => item.status === 'failed');
    const allNotDue = result.results.every(item => item.status === 'not_due');
    message(failed ? 'Some checks failed. Their failures are recorded; open Failures to see them.' : allNotDue ? 'No source is due yet. Your checking interval still applies.' : `Check complete: ${result.results.map(item => item.status.replaceAll('_', ' ')).join(', ')}.`, failed);
  } catch (error) { message(error.message, true); }
  finally { checking = false; $('#check-button').textContent = '↻ Run due check'; $('#check-button').disabled = !!data?.simulated; }
});
load();
