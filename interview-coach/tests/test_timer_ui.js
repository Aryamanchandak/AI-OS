// Run the page's real JavaScript: timer inputs are validated, saved and restored.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '../static/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function boot(storage) {
  const nodes = new Map();
  const document = {getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, {
      value: '', textContent: '', disabled: false,
      classList: {add(){}, remove(){}, toggle(){}}, querySelectorAll(){return [];},
    });
    return nodes.get(id);
  }};
  const requests = [];
  const context = vm.createContext({document, console, setTimeout, setInterval, clearInterval, performance,
    ...(storage ? {localStorage: storage} : {}),
    fetch: async (url, opts = {}) => {
      requests.push({url, body: opts.body && JSON.parse(opts.body)});
      return {ok: true, json: async () => url === '/api/question' ? {id: 'q1', question: 'Q'} : {context: ''}};
    }});
  vm.runInContext(script, context);
  return {document, requests, context, el: (id) => document.getElementById(id)};
}
const memory = () => { const m = {}; return {getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, m}; };

(async () => {
  const store = memory();
  let page = boot(store);
  page.el('prep').value = '45'; page.el('ans').value = '120';
  page.el('prep').oninput();
  page.el('ans').oninput();
  page = boot(store);                                   // "refresh"
  assert.equal(page.el('prep').value, 45);
  assert.equal(page.el('ans').value, 120);
  console.log('PASS UI: chosen timers survive a refresh');

  page.el('prep').value = '-1'; page.el('prep').oninput();   // invalid input is not saved
  assert.equal(JSON.parse(store.m['rehearsal.timers']).prep, 45);
  console.log('PASS UI: invalid values are not saved');

  for (const [prep, ans, ok] of [['0', '15', true], ['300', '600', true], ['-1', '90', false], ['301', '90', false],
      ['30', '14', false], ['30', '601', false], ['1.5', '90', false], ['30', '90.5', false],
      ['', '90', false], ['30', '', false], ['abc', '90', false], ['1e2', '90', false]]) {
    page = boot(memory());
    page.el('prep').value = prep; page.el('ans').value = ans;
    await page.el('newQ').onclick();
    const sent = page.requests.filter((r) => r.url === '/api/question');
    if (ok) {
      assert.deepEqual([sent[0].body.prep, sent[0].body.answer], [+prep, +ans], `${prep}/${ans}`);
    } else {
      assert.equal(sent.length, 0, `${prep}/${ans} must not reach the server`);
      assert(/whole number of seconds/.test(page.el('setupErr').textContent), `${prep}/${ans} needs a message`);
    }
  }
  console.log('PASS UI: boundaries are sent; bad values are blocked with a message');

  page = boot(null);                                    // no localStorage at all
  assert.equal(page.el('prep').value, '');
  page.el('prep').value = '30'; page.el('ans').value = '90';
  page.el('prep').oninput();
  await page.el('newQ').onclick();
  assert.equal(page.requests.filter((r) => r.url === '/api/question').length, 1);
  console.log('PASS UI: works when browser storage is unavailable');

  const bad = memory(); bad.m['rehearsal.timers'] = '{"prep":"abc","ans":99999}';
  page = boot(bad);
  assert.equal(page.el('prep').value, '');
  console.log('PASS UI: corrupt saved values are ignored');
})().catch((e) => { console.error(e); process.exitCode = 1; });
