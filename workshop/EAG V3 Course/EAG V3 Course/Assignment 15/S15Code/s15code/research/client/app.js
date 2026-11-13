'use strict';
const $ = id => document.getElementById(id);
let documents = [], researchRun = null, cardsRun = null, records = [], busy = false;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function status(message, error = false) { $('status').textContent = message; $('status').className = error ? 'error' : ''; }
function show(view) {
  document.querySelectorAll('.view').forEach(n => n.hidden = n.id !== view);
  document.querySelectorAll('[data-view]').forEach(n => n.setAttribute('aria-pressed', String(n.dataset.view === view)));
}
document.querySelectorAll('[data-view]').forEach(n => n.onclick = () => show(n.dataset.view));
async function request(path, body) {
  const response = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const data = await response.json(); message += ' ' + (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)); } catch {}
    throw Error(message);
  }
  return response.json();
}
async function work(message, action) {
  if (busy) return;
  busy = true; status(message);
  document.querySelectorAll('button,input,textarea,select').forEach(n => n.disabled = true);
  $('research-form').setAttribute('aria-busy','true');
  try { await action(); } catch (error) {
    status(error.message, true);
    const pending = document.querySelector('.loading-brief');
    if (pending) pending.textContent = 'No brief was produced. Review the error above and the run record, then try again.';
  }
  finally {
    busy = false;
    document.querySelectorAll('button,input,textarea,select').forEach(n => n.disabled = false);
    $('make-cards').disabled = !researchRun || researchRun.status !== 'completed';
    $('research-form').removeAttribute('aria-busy');
  }
}
function validateDocs(next) {
  if (next.length > 12 || next.some(d => !d.text.trim() || d.text.length > 100000) || next.reduce((n,d) => n+d.text.length,0) > 200000)
    throw Error('Use 1–12 nonempty sources, at most 100,000 characters each and 200,000 total.');
}
function invalidate() {
  researchRun = cardsRun = null; $('make-cards').disabled = true; $('cards').replaceChildren();
  $('brief').replaceChildren(element('p','Sources changed. Build a new brief to use them.','muted'));
}
function renderDocuments() {
  $('documents').replaceChildren(...documents.map((d,i) => {
    const item = element('li'); item.append(element('span',`${String(i+1).padStart(2,'0')} / ${d.name} · ${d.text.length.toLocaleString()} chars`));
    const remove = element('button','×','remove'); remove.type='button'; remove.setAttribute('aria-label',`Remove ${d.name}`);
    remove.onclick=()=>{documents.splice(i,1);invalidate();renderDocuments();};item.append(remove);return item;
  }));
}
$('example').onclick = () => work('Loading course sources…', async()=>{
  const example=await request('/v1/research/example'); validateDocs(example.documents); documents=example.documents;
  $('question').value=example.question;invalidate();renderDocuments();status('Course example ready. Build your brief when you are ready.');
});
$('files').onchange = () => {
  const files=Array.from($('files').files);
  work('Reading your files…',async()=>{
    const added=[];
    for(const file of files){
      if(!/\.(md|txt)$/i.test(file.name) || file.size>400000) throw Error('Choose .md or .txt files smaller than 400 KB.');
      added.push({name:file.name,text:await file.text()});
    }
    validateDocs([...documents,...added]); documents.push(...added); invalidate(); renderDocuments(); status('Sources added.');
  }).finally(()=>$('files').value='');
};
$('add-text').onclick=()=>work('Adding source…',async()=>{
  const doc={name:$('source-name').value.trim()||'Pasted source',text:$('source-text').value};
  validateDocs([...documents,doc]);documents.push(doc);invalidate();renderDocuments();$('source-text').value='';status('Source added.');
});
function budget(){const value=Number($('budget').value);if(!(value>0&&value<=10))throw Error('Set a budget greater than zero and at most $10.');return value;}
function cited(claim, evidence) {
  const box=element('div',undefined,'claim');box.append(element('p',claim.text));
  for(const citation of claim.citations){
    const source=evidence.find(e=>e.id===citation.evidence_id);
    const detail=element('details',undefined,'citation');
    detail.append(element('summary',source?`${source.document} · lines ${source.line_start}–${source.line_end}`:citation.evidence_id),
      element('blockquote',citation.quote),element('pre',source?.text||'Source unavailable','passage'));box.append(detail);
  }
  return box;
}
function remember(run) {
  records.push(run);
  const item=element('article',undefined,'record');
  const charges=run.budget.charges||[];
  item.append(element('strong',`${run.kind.toUpperCase()} / ${run.status}`),element('p',
    `$${Number(run.budget.spent||0).toFixed(6)} spent · ${charges.length} calls · ${charges.map(c=>`${c.tier} / ${c.model}`).join(', ')||'No model called'}`,'metrics'));
  const detail=element('details');detail.append(element('summary',`Run ${run.run_id} · trace ${run.trace.trace_id}`),element('pre',JSON.stringify(run,null,2)));item.append(detail);$('records').prepend(item);
  if(run.status!=='completed')throw Error(`${run.status==='refused'?'Budget refused the call':'Run failed'}: ${run.error||'See run record.'}`);
}
$('research-form').onsubmit=event=>{
  event.preventDefault();
  work('Reading sources and building your brief…',async()=>{
    if(!documents.length)throw Error('Add at least one source first.');
    researchRun=null;cardsRun=null;$('cards').replaceChildren();
    $('brief').replaceChildren(element('p','Building a new brief…','muted loading-brief'));
    const run=await request('/v1/research/runs',{question:$('question').value,documents,budget:budget(),strategy:$('strategy').value});
    remember(run);researchRun=run;
    const output=run.output;const target=$('brief');target.replaceChildren(element('p','03 / DECISION BRIEF','eyebrow'),element('h2',output.title));
    for(const [title,claims] of [['Supported conclusions',output.conclusions],['Competing explanations & tradeoffs',output.alternatives]]){
      target.append(element('h3',title));claims.forEach(c=>target.append(cited(c,run.evidence)));
    }
    target.append(element('h3','What remains uncertain'));const list=element('ul');output.uncertainties.forEach(t=>list.append(element('li',t)));target.append(list);
    show('brief');status(`Brief ready. $${run.budget.spent.toFixed(6)} recorded. Open any citation to inspect its source.`);
  });
};
$('make-cards').onclick=()=>work('Turning your sources into study cards…',async()=>{
  const run=await request('/v1/research/cards',{research_run_id:researchRun.run_id,budget:budget()});remember(run);cardsRun=run;
  $('cards').replaceChildren(...run.output.cards.map((card,index)=>{
    const box=element('article',undefined,'card');box.append(element('p',`CARD ${index+1} / ${run.output.cards.length}`,'eyebrow'),element('h3',card.question));
    const label=element('label','Your recall answer');label.htmlFor=`recall-${index}`;const answer=element('textarea');answer.id=label.htmlFor;answer.rows=3;answer.maxLength=4000;
    const feedback=element('div',undefined,'feedback');feedback.setAttribute('aria-live','polite');
    const grade=element('button','Check my recall ↗');grade.type='button';grade.onclick=()=>work('Checking recall against the sources…',async()=>{
      if(!answer.value.trim())throw Error('Write your recall answer first.');
      const result=await request('/v1/research/grade',{cards_run_id:cardsRun.run_id,card_index:index,answer:answer.value,budget:budget()});remember(result);
      feedback.replaceChildren(element('strong',result.output.verdict.toUpperCase()),cited(result.output.explanation,result.evidence));status('Recall checked. Feedback and its sources are below your answer.');
    });
    const reveal=element('details');reveal.append(element('summary','Reveal source-backed answer'),cited(card.answer,run.evidence));
    box.append(label,answer,grade,feedback,reveal);return box;
  }));show('study');status('Study cards ready. Try an answer before revealing the source-backed answer.');
});
