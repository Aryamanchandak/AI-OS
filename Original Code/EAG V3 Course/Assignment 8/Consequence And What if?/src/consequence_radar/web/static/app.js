const form = document.querySelector('#batch-form');
if (form) form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = document.querySelector('#form-status');
  const button = form.querySelector('button');
  const urls = document.querySelector('#news').value.split(/\n+/).map(value => value.trim()).filter(Boolean);
  const invalidUrl = urls.find(value => {
    try {
      const parsed = new URL(value);
      return !['http:', 'https:'].includes(parsed.protocol);
    } catch {
      return true;
    }
  });

  status.classList.remove('is-error');
  if (urls.length < 1 || urls.length > 100 || invalidUrl) {
    status.textContent = 'Enter 1–100 complete http:// or https:// article URLs, one per line.';
    status.classList.add('is-error');
    return;
  }

  status.textContent = 'Starting research run…';
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch('/api/v1/runs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({items:urls.map(url => ({url}))})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail?.[0]?.msg || data.detail || 'The run could not be started. Please try again.');
    window.location.assign(data.url);
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : 'The run could not be started. Please try again.';
    status.classList.add('is-error');
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
});
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => { await navigator.clipboard.writeText(button.dataset.copy); button.textContent='Copied'; }));
if (window.RADAR_RUNNING) {
  const stream = new EventSource(`/api/v1/runs/${window.RADAR_RUN_ID}/events`); const list = document.querySelector('#events');
  stream.onmessage = event => { const data=JSON.parse(event.data); const li=document.createElement('li'); li.textContent=data.message; list.append(li); if (['complete','error'].includes(data.kind)) { stream.close(); setTimeout(()=>location.reload(),350); } };
}
