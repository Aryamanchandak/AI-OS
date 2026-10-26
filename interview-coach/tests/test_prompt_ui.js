// Run the page's actual JavaScript with a small DOM and HTTP simulation.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '../static/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const nodes = new Map();
const document = {getElementById(id) {
  if (!nodes.has(id)) nodes.set(id, {
    value: '', textContent: '', disabled: false,
    classList: {add(){}, remove(){}, toggle(){}}, querySelectorAll(){return [];},
  });
  return nodes.get(id);
}};
const defaults = {question: 'Default questions', evaluation: 'Default evaluation'};
let saved = {...defaults};
let fail = false;
const context = vm.createContext({document, console, setTimeout, setInterval, clearInterval,
  fetch: async (url, opts = {}) => {
    if (url === '/api/prompts') {
      if (fail) throw new Error('Offline');
      if (opts.method === 'POST') {
        const body = JSON.parse(opts.body);
        saved = body.reset ? {...defaults} : body;
      }
      return {ok: true, json: async () => ({...saved})};
    }
    return {ok: true, json: async () => url === '/api/history' ? [] : {context: ''}};
  },
});
(async () => {
  vm.runInContext(script, context);
  await context.updatePrompts();
  assert.equal(document.getElementById('questionPrompt').value, defaults.question);
  assert.equal(document.getElementById('evaluationPrompt').value, defaults.evaluation);
  assert.equal(document.getElementById('savePrompts').disabled, false);
  console.log('PASS UI: both current prompts load into editable fields');
  document.getElementById('questionPrompt').value = 'Custom questions';
  document.getElementById('evaluationPrompt').value = 'Custom evaluation';
  document.getElementById('questionPrompt').oninput();
  assert(document.getElementById('promptStatus').textContent.includes('Unsaved'));
  await document.getElementById('savePrompts').onclick();
  assert.equal(saved.question, 'Custom questions');
  assert.equal(saved.evaluation, 'Custom evaluation');
  await context.updatePrompts();
  assert.equal(document.getElementById('questionPrompt').value, 'Custom questions');
  console.log('PASS UI: save sends both edited prompts and reload preserves them');
  fail = true;
  document.getElementById('questionPrompt').value = 'Keep this draft';
  await document.getElementById('savePrompts').onclick();
  assert.equal(document.getElementById('questionPrompt').value, 'Keep this draft');
  assert.equal(document.getElementById('savePrompts').disabled, false);
  assert(document.getElementById('promptStatus').textContent.includes('Could not save'));
  console.log('PASS UI: save failure preserves draft and allows retry');
  await context.updatePrompts();
  assert.equal(document.getElementById('savePrompts').disabled, true);
  assert.equal(document.getElementById('reloadPrompts').disabled, false);
  fail = false;
  await document.getElementById('reloadPrompts').onclick();
  assert.equal(document.getElementById('savePrompts').disabled, false);
  await document.getElementById('resetPrompts').onclick();
  assert.deepEqual(saved, defaults);
  assert.equal(document.getElementById('evaluationPrompt').value, defaults.evaluation);
  console.log('PASS UI: load failure can recover; reset saves and displays defaults');
})().catch(error => {console.error(error); process.exitCode = 1;});
