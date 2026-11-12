import { useMemo, useState } from 'react';
import type { AuditReport, DecisionRecord, PraxisResult } from '../shared/types';
import { PraxisApi } from './api';

type View = 'LIVE' | 'STRIP' | 'REP' | 'AUDIT' | 'TRACKER' | 'LIBRARY';
type LoadState = 'idle' | 'loading' | 'success' | 'error';

const PRIMARY_VIEWS: Array<{ id: View; label: string; note: string }> = [
  { id: 'LIVE', label: 'LIVE', note: 'One move' },
  { id: 'STRIP', label: 'STRIP', note: 'One variable' },
  { id: 'REP', label: 'REP', note: 'One drill' },
  { id: 'AUDIT', label: 'AUDIT', note: 'The record' },
];

export function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('praxis-token') ?? '');
  const [draftToken, setDraftToken] = useState(token);

  if (!token) {
    return (
      <main className="auth-shell">
        <section className="auth-card entrance">
          <p className="wordmark">PRAXIS<span>·</span></p>
          <p className="eyebrow">Private local access</p>
          <h1>Bring the situation.<br />Leave with the move.</h1>
          <form onSubmit={(event) => {
            event.preventDefault();
            const clean = draftToken.trim();
            if (clean.length < 12) return;
            sessionStorage.setItem('praxis-token', clean);
            setToken(clean);
          }}>
            <label htmlFor="access-token">Access token</label>
            <input id="access-token" type="password" autoComplete="current-password" value={draftToken} onChange={(event) => setDraftToken(event.target.value)} placeholder="From PRAXIS_ACCESS_TOKEN" />
            <button type="submit" disabled={draftToken.trim().length < 12}>Enter PRAXIS <span aria-hidden="true">→</span></button>
          </form>
          <p className="privacy-note">Held only for this browser tab. Your API key never reaches this screen.</p>
        </section>
      </main>
    );
  }

  return <PraxisWorkspace token={token} onLock={() => { sessionStorage.removeItem('praxis-token'); setToken(''); setDraftToken(''); }} />;
}

function PraxisWorkspace({ token, onLock }: { token: string; onLock: () => void }) {
  const api = useMemo(() => new PraxisApi(token), [token]);
  const [view, setView] = useState<View>('LIVE');

  return (
    <div className="app-shell">
      <header className="topbar entrance">
        <button className="wordmark wordmark-button" type="button" onClick={() => setView('LIVE')}>PRAXIS<span>·</span></button>
        <nav className="utility-nav" aria-label="Utilities">
          <button type="button" className={view === 'TRACKER' ? 'active' : ''} onClick={() => setView('TRACKER')}>Tracker</button>
          <button type="button" className={view === 'LIBRARY' ? 'active' : ''} onClick={() => setView('LIBRARY')}>Library</button>
          <button type="button" onClick={onLock}>Lock</button>
        </nav>
      </header>

      <aside className="mode-rail entrance delay-1" aria-label="PRAXIS modes">
        {PRIMARY_VIEWS.map((item) => (
          <button key={item.id} type="button" className={view === item.id ? 'active' : ''} onClick={() => setView(item.id)}>
            <strong>{item.label}</strong><span>{item.note}</span>
          </button>
        ))}
      </aside>

      <main className="workspace entrance delay-2">
        {(view === 'LIVE' || view === 'STRIP') && <DecisionView key={view} mode={view} api={api} />}
        {view === 'REP' && <RepView api={api} />}
        {view === 'AUDIT' && <AuditView api={api} />}
        {view === 'TRACKER' && <TrackerView api={api} />}
        {view === 'LIBRARY' && <LibraryView api={api} />}
      </main>

      <footer className="statusline"><span>LOCAL / PRIVATE</span><span>NO HOROSCOPES</span></footer>
    </div>
  );
}

function DecisionView({ mode, api }: { mode: 'LIVE' | 'STRIP'; api: PraxisApi }) {
  const [situation, setSituation] = useState('');
  const [state, setState] = useState<LoadState>('idle');
  const [result, setResult] = useState<PraxisResult>();
  const [error, setError] = useState('');
  const clean = situation.trim();
  const validation = clean.length > 0 && clean.length < 12 ? 'Give PRAXIS at least 12 characters of context.' : clean.length > 4000 ? 'Cut the situation to 4,000 characters.' : '';

  async function submit() {
    if (validation || !clean) return;
    setState('loading'); setError(''); setResult(undefined);
    try {
      const response = await api.run({ mode, situation: clean });
      setResult(response.result); setState('success');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The request failed.'); setState('error');
    }
  }

  return (
    <section className="decision-layout">
      <div className="prompt-column">
        <p className="eyebrow">{mode === 'LIVE' ? 'Operational counsel' : 'Decision reduction'}</p>
        <h1>{mode === 'LIVE' ? 'What is happening?' : 'What are you overcomplicating?'}</h1>
        <p className="lede">{mode === 'LIVE' ? 'Give the facts, the actors, and the decision. PRAXIS returns one move—or refuses.' : 'Put the whole knot here. PRAXIS finds the strand carrying the weight.'}</p>
        <label htmlFor="situation" className="sr-only">Situation</label>
        <textarea id="situation" value={situation} onChange={(event) => setSituation(event.target.value)} placeholder="My PM keeps reopening a decision we closed last week…" maxLength={4000} aria-describedby="situation-meta" aria-invalid={Boolean(validation)} />
        <div id="situation-meta" className="input-meta"><span className={validation ? 'validation' : ''}>{validation || 'Facts beat framing.'}</span><span>{situation.length}/4000</span></div>
        <button className="primary-action" type="button" disabled={!clean || Boolean(validation) || state === 'loading'} onClick={submit}>
          {state === 'loading' ? <><span className="spinner" /> Cutting through</> : <>Make the call <span aria-hidden="true">→</span></>}
        </button>
      </div>
      <OutputPanel state={state} result={result} error={error} />
    </section>
  );
}

function OutputPanel({ state, result, error }: { state: LoadState; result?: PraxisResult; error: string }) {
  return (
    <aside className={`output-panel ${state}`} aria-live="polite" aria-busy={state === 'loading'}>
      <div className="output-index">01 / OUTPUT</div>
      {state === 'idle' && <div className="empty-output"><span>—</span><p>The answer will be shorter than the problem.</p></div>}
      {state === 'loading' && <div className="loading-output"><span className="scanline" /><p>Matching situational cues.<br />Discarding noise.</p></div>}
      {state === 'error' && <div className="error-output"><p className="eyebrow">Halted</p><h2>No clean answer.</h2><p>{error}</p></div>}
      {state === 'success' && result && (
        <div className="answer-output entrance">
          <p className="answer-kind">{result.kind === 'question' ? 'One missing fact' : result.kind === 'null' ? 'NULL' : result.mode}</p>
          <p className="answer-copy">{result.content}</p>
          {result.card && <div className="card-proof"><span>{result.card.id}</span><span>{result.card.replication}</span><p>{result.card.source}</p></div>}
        </div>
      )}
    </aside>
  );
}

function RepView({ api }: { api: PraxisApi }) {
  const [state, setState] = useState<LoadState>('idle');
  const [error, setError] = useState('');
  const [rep, setRep] = useState<{ cardId: string; cardClaim: string; scenario: string; successCriterion: string }>();
  const [revealed, setRevealed] = useState(false);
  async function generate() {
    setState('loading'); setError(''); setRevealed(false);
    try { setRep(await api.rep()); setState('success'); } catch (caught) { setError(caught instanceof Error ? caught.message : 'REP failed.'); setState('error'); }
  }
  return (
    <section className="single-view">
      <p className="eyebrow">Targeted rehearsal</p><h1>Train the gap.<br />Not the favorite.</h1>
      <p className="lede">REP selects the card you have never fired—or the one your outcomes say you misuse.</p>
      <button className="primary-action compact" type="button" onClick={generate} disabled={state === 'loading'}>{state === 'loading' ? 'Building pressure…' : 'Generate the drill →'}</button>
      {state === 'error' && <p className="inline-error">{error}</p>}
      {rep && <article className="rep-card entrance"><p className="output-index">COVERAGE GAP / {rep.cardId}</p><h2>{rep.scenario}</h2><button type="button" className="text-action" onClick={() => setRevealed(!revealed)}>{revealed ? 'Hide criterion' : 'Reveal success criterion'}</button>{revealed && <div className="criterion"><p>{rep.successCriterion}</p><span>{rep.cardClaim}</span></div>}</article>}
    </section>
  );
}

function AuditView({ api }: { api: PraxisApi }) {
  const [state, setState] = useState<LoadState>('idle');
  const [report, setReport] = useState<AuditReport>();
  const [error, setError] = useState('');
  async function load() { setState('loading'); setError(''); try { setReport(await api.audit()); setState('success'); } catch (caught) { setError(caught instanceof Error ? caught.message : 'Audit failed.'); setState('error'); } }
  return (
    <section className="single-view">
      <div className="view-heading"><div><p className="eyebrow">Weekly accountability</p><h1>Coverage,<br />without comfort.</h1></div><button className="primary-action compact" type="button" onClick={load} disabled={state === 'loading'}>{state === 'loading' ? 'Calculating…' : report ? 'Refresh audit' : 'Run audit →'}</button></div>
      {state === 'idle' && <p className="empty-message">No report loaded. Run the audit against every card and resolved prediction.</p>}
      {state === 'error' && <p className="inline-error">{error}</p>}
      {report && <><div className="metrics"><Metric label="Coverage" value={`${report.coveragePercent}%`} /><Metric label="Never fired" value={String(report.neverFired)} /><Metric label="Unresolved" value={String(report.unresolved)} /><Metric label="Resolved" value={String(report.resolved)} /></div><div className="audit-list">{report.cards.map((card) => <article key={card.cardId}><div><span>{card.cardId}</span><strong>{card.claim}</strong></div><div className="audit-stats"><span>{card.fired} fired</span><span>{card.hitRate === null ? '—' : `${Math.round(card.hitRate * 100)}%`} hit</span><span>{card.personalWeight.toFixed(2)} weight</span></div></article>)}</div></>}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }

function TrackerView({ api }: { api: PraxisApi }) {
  const [state, setState] = useState<LoadState>('idle');
  const [items, setItems] = useState<DecisionRecord[]>([]);
  const [error, setError] = useState('');
  async function load() { setState('loading'); setError(''); try { setItems(await api.decisions()); setState('success'); } catch (caught) { setError(caught instanceof Error ? caught.message : 'Tracker failed.'); setState('error'); } }
  return <section className="single-view"><div className="view-heading"><div><p className="eyebrow">Prediction ledger</p><h1>Score the claim.<br />Not the story.</h1></div><button className="primary-action compact" type="button" onClick={load} disabled={state === 'loading'}>{state === 'loading' ? 'Loading…' : items.length ? 'Refresh' : 'Load decisions →'}</button></div>{state === 'idle' && <p className="empty-message">Load your emitted predictions, then mark what actually happened.</p>}{error && <p className="inline-error">{error}</p>}<div className="tracker-list">{items.map((item) => <DecisionItem key={item.id} item={item} api={api} onResolved={load} />)}</div></section>;
}

function DecisionItem({ item, api, onResolved }: { item: DecisionRecord; api: PraxisApi; onResolved: () => Promise<void> }) {
  const [outcome, setOutcome] = useState(item.outcome ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  async function resolve(hit: boolean) { if (!outcome.trim()) { setError('Write the outcome before scoring it.'); return; } setSaving(true); setError(''); try { await api.resolve(item.id, hit, outcome.trim()); await onResolved(); } catch (caught) { setError(caught instanceof Error ? caught.message : 'Resolution failed.'); } finally { setSaving(false); } }
  return <article className="decision-item"><div className="decision-meta"><span>{item.mode}</span><span>{new Date(item.createdAt).toLocaleDateString()}</span><span className={item.status}>{item.status}</span></div><h2>{item.situation}</h2><p className="decision-answer">{item.result.content}</p>{item.status === 'open' ? <div className="resolution"><label htmlFor={`outcome-${item.id}`}>What happened?</label><textarea id={`outcome-${item.id}`} value={outcome} onChange={(event) => setOutcome(event.target.value)} maxLength={2000} /><div><button type="button" disabled={saving} onClick={() => resolve(true)}>Prediction hit</button><button type="button" disabled={saving} onClick={() => resolve(false)}>Prediction missed</button></div>{error && <p className="validation">{error}</p>}</div> : <p className="resolved-outcome"><strong>{item.predictionMet ? 'HIT' : 'MISS'}</strong> {item.outcome}</p>}</article>;
}

function LibraryView({ api }: { api: PraxisApi }) {
  const [title, setTitle] = useState(''); const [author, setAuthor] = useState(''); const [sourceText, setSourceText] = useState('');
  const [state, setState] = useState<LoadState>('idle'); const [message, setMessage] = useState(''); const [graph, setGraph] = useState<{ cards: unknown[]; cues: string[]; cardCueEdges: unknown[]; contradictions: unknown[] }>();
  const valid = title.trim() && author.trim() && sourceText.trim().length >= 500;
  async function ingest() { if (!valid) return; setState('loading'); setMessage(''); try { const result = await api.ingest({ title: title.trim(), author: author.trim(), sourceText: sourceText.trim() }); setMessage(`${result.cards.length} cards extracted; ${result.passageCount} grounding passages stored.`); setGraph(await api.graph()); setState('success'); setSourceText(''); } catch (caught) { setMessage(caught instanceof Error ? caught.message : 'Ingestion failed.'); setState('error'); } }
  async function inspectGraph() { setState('loading'); try { setGraph(await api.graph()); setState('success'); } catch (caught) { setMessage(caught instanceof Error ? caught.message : 'Graph failed.'); setState('error'); } }
  return <section className="single-view"><p className="eyebrow">Corpus workshop</p><h1>Destroy the book.<br />Keep the moves.</h1><p className="lede">Paste source text you are entitled to use. PRAXIS extracts atomic cards and retains passages for boundary-condition grounding.</p><div className="library-grid"><div className="ingest-form"><label htmlFor="book-title">Book or source title</label><input id="book-title" value={title} onChange={(event) => setTitle(event.target.value)} /><label htmlFor="book-author">Author</label><input id="book-author" value={author} onChange={(event) => setAuthor(event.target.value)} /><label htmlFor="source-text">Source text</label><textarea id="source-text" value={sourceText} onChange={(event) => setSourceText(event.target.value)} maxLength={200000} /><div className="input-meta"><span>Minimum 500 characters</span><span>{sourceText.length}</span></div><button className="primary-action compact" type="button" disabled={!valid || state === 'loading'} onClick={ingest}>{state === 'loading' ? 'Extracting…' : 'Extract cards →'}</button>{message && <p className={state === 'error' ? 'inline-error' : 'success-message'}>{message}</p>}</div><aside className="graph-summary"><p className="output-index">CARD / CUE GRAPH</p>{graph ? <><Metric label="Cards" value={String(graph.cards.length)} /><Metric label="Cue nodes" value={String(graph.cues.length)} /><Metric label="HAS_CUE edges" value={String(graph.cardCueEdges.length)} /><Metric label="Contradictions" value={String(graph.contradictions.length)} /></> : <><p>The graph stores cards, controlled cues, and explicit contradiction edges.</p><button type="button" className="text-action" onClick={inspectGraph}>Inspect graph</button></>}</aside></div></section>;
}
