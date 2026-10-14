'use client';

import { useState, useEffect, useCallback } from 'react';
import { detectSections, extractContext, iterateSection } from '@/lib/operations';
import { snapshotDocument } from '@/lib/versioning';
import { loadDocument, saveDocument, loadContext, saveContext, loadVersions, saveVersions } from '@/lib/storage';
import { DEFAULT_GUIDE_PROMPT } from '@/lib/prompts';
import type { Section, ProjectContext, Version, Document, Mode } from '@/lib/types';

// ── Colour tokens ──────────────────────────────────────────────────────────
const C = {
  bg:       '#0d0e0f',
  surface:  '#161718',
  elevated: '#1e1f21',
  border:   '#2a2b2d',
  txt:      '#e8e6e1',
  muted:    '#9a9690',
  dim:      '#5a5855',
  accent:   '#c9a66b',
  accentDim:'#4a3a20',
  green:    '#7aaa74',
  greenBg:  '#192b17',
  red:      '#c97b6b',
  redBg:    '#2e1a1d',
} as const;

// ── Tiny style helpers ─────────────────────────────────────────────────────
const label: React.CSSProperties = {
  fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.09em',
  color: C.dim, fontFamily: 'var(--font-geist-sans)', marginBottom: 6,
};
const btn = (active = false, danger = false): React.CSSProperties => ({
  background: active ? C.accent : C.elevated,
  color: active ? C.bg : danger ? C.red : C.txt,
  border: `1px solid ${active ? C.accent : C.border}`,
  borderRadius: 4, padding: '3px 10px', fontSize: 12,
  cursor: 'pointer', fontFamily: 'var(--font-geist-sans)',
  transition: 'background 120ms, border-color 120ms',
});
const textarea: React.CSSProperties = {
  width: '100%', background: C.elevated, color: C.txt, border: `1px solid ${C.border}`,
  borderRadius: 6, padding: '12px 14px', fontFamily: 'var(--font-geist-mono)',
  fontSize: 14, resize: 'vertical', outline: 'none', boxSizing: 'border-box',
  lineHeight: 1.7,
};

// ── Main component ─────────────────────────────────────────────────────────
export default function Home() {
  const [mode, setMode]                   = useState<Mode>('prompt');
  const [guidePrompt, setGuidePrompt]     = useState(DEFAULT_GUIDE_PROMPT);
  const [showGuide, setShowGuide]         = useState(false);
  const [contextRaw, setContextRaw]       = useState('');
  const [projectContext, setProjectContext] = useState<ProjectContext | null>(null);
  const [rawInput, setRawInput]           = useState('');
  const [doc, setDoc]                     = useState<Document | null>(null);
  const [versions, setVersions]           = useState<Version[]>([]);
  const [busy, setBusy]                   = useState('');
  const [error, setError]                 = useState('');

  // Per-section state
  const [drafts, setDrafts]           = useState<Record<string, string>>({});
  const [suggestions, setSuggestions] = useState<Record<string, string>>({});
  const [sectionBusy, setSectionBusy] = useState<Record<string, boolean>>({});
  const [flashed, setFlashed]         = useState<Record<string, boolean>>({});
  const [stitched, setStitched]       = useState(false);

  // ── Hydrate from localStorage on mount ──────────────────────────────────
  useEffect(() => {
    const savedDoc = loadDocument();
    const savedCtx = loadContext();
    const savedVer = loadVersions();
    if (savedDoc) {
      setDoc(savedDoc);
      setMode(savedDoc.mode);
      const init: Record<string, string> = {};
      savedDoc.sections.forEach(s => { init[s.id] = s.content; });
      setDrafts(init);
    }
    if (savedCtx) { setProjectContext(savedCtx); setContextRaw(savedCtx.raw); }
    if (savedVer.length) setVersions(savedVer);
  }, []);

  const wrap = useCallback(async (lbl: string, fn: () => Promise<void>) => {
    setBusy(lbl); setError('');
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(''); }
  }, []);

  // ── Handlers ──────────────────────────────────────────────────────────
  const handleExtractContext = () => wrap('Extracting context…', async () => {
    if (!contextRaw.trim()) return;
    const ctx = await extractContext(contextRaw);
    setProjectContext(ctx);
    saveContext(ctx);
  });

  const handleAnalyze = () => wrap('Detecting sections…', async () => {
    if (!rawInput.trim()) return;
    const sections = await detectSections(rawInput, mode);
    const newDoc: Document = { id: crypto.randomUUID(), mode, rawInput, sections, testCases: [] };
    const init: Record<string, string> = {};
    sections.forEach(s => { init[s.id] = s.content; });
    setDrafts(init);
    setSuggestions({});
    setSectionBusy({});
    setFlashed({});
    setDoc(newDoc);
    setVersions([]);
    saveDocument(newDoc);
    saveVersions([]);
  });

  const handleSaveSection = useCallback((sectionId: string, currentDoc: Document, currentDrafts: Record<string, string>, currentVersions: Version[]) => {
    const section = currentDoc.sections.find(s => s.id === sectionId);
    if (!section) return;
    const newContent = currentDrafts[sectionId] ?? section.content;
    if (newContent === section.content) return;

    const updatedSection: Section = {
      ...section,
      content: newContent,
      history: [...section.history, {
        timestamp: Date.now(),
        userMessage: 'manual edit',
        oldContent: section.content,
        newContent,
        reasoning: 'User edited directly',
      }],
    };
    const updatedDoc: Document = {
      ...currentDoc,
      sections: currentDoc.sections.map(s => s.id === sectionId ? updatedSection : s),
    };
    setDoc(updatedDoc);
    saveDocument(updatedDoc);

    const snapshot = snapshotDocument(updatedDoc, {}, []);
    const newVersions = [...currentVersions, snapshot];
    setVersions(newVersions);
    saveVersions(newVersions);
  }, []);

  const handleApplySuggestion = useCallback(async (sectionId: string) => {
    if (!doc) return;
    const section = doc.sections.find(s => s.id === sectionId);
    if (!section || !suggestions[sectionId]?.trim()) return;

    setSectionBusy(prev => ({ ...prev, [sectionId]: true }));
    setError('');
    try {
      const fullDocText = doc.sections.map(s => `[§${s.id} ${s.title}]\n${s.content}`).join('\n\n');
      const result = await iterateSection({
        mode, section, fullDocument: fullDocText,
        projectContext, chatHistory: [],
        userMessage: suggestions[sectionId],
        guidePrompt,
      });

      if (result.rewrittenContent && result.rewrittenContent !== section.content) {
        const updatedSection: Section = {
          ...section,
          content: result.rewrittenContent,
          history: [...section.history, {
            timestamp: Date.now(),
            userMessage: suggestions[sectionId],
            oldContent: section.content,
            newContent: result.rewrittenContent,
            reasoning: result.reasoning,
          }],
        };
        const updatedDoc: Document = {
          ...doc,
          sections: doc.sections.map(s => s.id === sectionId ? updatedSection : s),
        };
        setDoc(updatedDoc);
        saveDocument(updatedDoc);
        setDrafts(prev => ({ ...prev, [sectionId]: result.rewrittenContent }));

        const snapshot = snapshotDocument(updatedDoc, {}, []);
        const newVersions = [...versions, snapshot];
        setVersions(newVersions);
        saveVersions(newVersions);

        setFlashed(prev => ({ ...prev, [sectionId]: true }));
        setTimeout(() => setFlashed(prev => ({ ...prev, [sectionId]: false })), 1500);
      }
      setSuggestions(prev => ({ ...prev, [sectionId]: '' }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSectionBusy(prev => ({ ...prev, [sectionId]: false }));
    }
  }, [doc, suggestions, mode, projectContext, guidePrompt, versions]);

  const handleStitch = async () => {
    if (!doc) return;
    const content = doc.sections.map(s => s.content).join('\n\n');
    await navigator.clipboard.writeText(content);
    setStitched(true);
    setTimeout(() => setStitched(false), 2000);
  };

  // ── Onboarding screen ─────────────────────────────────────────────────
  if (!doc) {
    return (
      <div style={{ background: C.bg, color: C.txt, minHeight: '100vh', fontFamily: 'var(--font-geist-sans)' }}>
        {/* Top bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 20px', height: 44, borderBottom: `1px solid ${C.border}` }}>
          <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: '-0.01em' }}>Optimizer</span>
          <div style={{ display: 'flex', gap: 4, marginLeft: 8 }}>
            <button style={btn(mode === 'prompt')} onClick={() => setMode('prompt')}>Prompt</button>
            <button style={btn(mode === 'plan')}   onClick={() => setMode('plan')}>Plan</button>
          </div>
          <span style={{ marginLeft: 'auto', fontSize: 11, color: C.dim }}>{busy}</span>
        </div>

        <div style={{ maxWidth: 680, margin: '0 auto', padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: 28 }}>

          {/* Guide prompt accordion */}
          <section>
            <button
              onClick={() => setShowGuide(g => !g)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, padding: 0, color: C.txt, fontFamily: 'var(--font-geist-sans)', width: '100%' }}
            >
              <span style={{ fontSize: 12, fontWeight: 600 }}>Optimization guide</span>
              <span style={{ fontSize: 11, color: C.muted, flex: 1, textAlign: 'left' }}>— the prompt the AI uses to optimize your content</span>
              <span style={{ fontSize: 11, color: C.dim }}>{showGuide ? '▲ hide' : '▼ show'}</span>
            </button>
            {showGuide && (
              <div style={{ marginTop: 10 }}>
                <p style={{ fontSize: 11, color: C.muted, marginBottom: 8, lineHeight: 1.6 }}>
                  Edit this to change how the AI behaves when you ask it to explain or rewrite sections.
                </p>
                <textarea
                  style={{ ...textarea, minHeight: 180 }}
                  value={guidePrompt}
                  onChange={e => setGuidePrompt(e.target.value)}
                />
                <button
                  style={{ ...btn(), marginTop: 6, fontSize: 11 }}
                  onClick={() => setGuidePrompt(DEFAULT_GUIDE_PROMPT)}
                >
                  Reset to default
                </button>
              </div>
            )}
          </section>

          {/* Project context */}
          <section>
            <p style={label}>Project context</p>
            <p style={{ fontSize: 12, color: C.muted, marginBottom: 8, lineHeight: 1.6 }}>
              Dump anything — bullets, ramblings, half a tech spec. The AI will structure it and use it in every call.
            </p>
            <textarea
              style={{ ...textarea, minHeight: 100 }}
              value={contextRaw}
              onChange={e => setContextRaw(e.target.value)}
              placeholder="What you're building, tech stack, constraints, decisions already made…"
            />
            <button style={{ ...btn(), marginTop: 8 }} onClick={handleExtractContext} disabled={!!busy || !contextRaw.trim()}>
              {busy === 'Extracting context…' ? 'Extracting…' : 'Extract context'}
            </button>
            {projectContext && (
              <div style={{ marginTop: 10, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6, padding: '10px 12px' }}>
                <p style={{ ...label, marginBottom: 8 }}>Extracted</p>
                {Object.entries(projectContext.extracted).map(([k, v]) => (
                  <div key={k} style={{ marginBottom: 6 }}>
                    <span style={{ fontSize: 11, color: C.muted, textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}:</span>{' '}
                    <span style={{ fontSize: 12, color: C.txt }}>
                      {Array.isArray(v) ? (v.length ? v.join(', ') : '—') : v || '—'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Document input */}
          <section>
            <p style={label}>Your {mode === 'prompt' ? 'prompt' : 'plan'}</p>
            <textarea
              style={{ ...textarea, minHeight: 260 }}
              value={rawInput}
              onChange={e => setRawInput(e.target.value)}
              placeholder={mode === 'prompt'
                ? 'Paste a full prompt — sections will be auto-detected.'
                : 'Paste a markdown plan — sections will be auto-detected.'}
            />
            <div style={{ marginTop: 10, display: 'flex', gap: 8, alignItems: 'center' }}>
              <button
                style={{ ...btn(true), padding: '6px 16px', fontSize: 13 }}
                onClick={handleAnalyze}
                disabled={!!busy || !rawInput.trim()}
              >
                {busy === 'Detecting sections…' ? 'Analyzing…' : 'Analyze & split into sections'}
              </button>
              {!projectContext && (
                <span style={{ fontSize: 11, color: C.dim }}>tip: add project context above first</span>
              )}
            </div>
          </section>

          {error && (
            <div style={{ background: C.redBg, border: `1px solid ${C.red}`, borderRadius: 6, padding: '10px 12px', fontSize: 12, color: C.red }}>
              {error}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Section cards view ────────────────────────────────────────────────
  return (
    <div style={{ background: C.bg, color: C.txt, minHeight: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-geist-sans)' }}>

      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '0 20px', height: 44,
        borderBottom: `1px solid ${C.border}`, fontSize: 12,
        position: 'sticky', top: 0, background: C.bg, zIndex: 10,
      }}>
        <span style={{ fontWeight: 600, fontSize: 13, letterSpacing: '-0.01em', marginRight: 4 }}>Optimizer</span>
        <div style={{ display: 'flex', gap: 3 }}>
          <button style={btn(mode === 'prompt')} onClick={() => setMode('prompt')}>Prompt</button>
          <button style={btn(mode === 'plan')}   onClick={() => setMode('plan')}>Plan</button>
        </div>
        <span style={{ color: C.border }}>·</span>
        <button style={btn()} onClick={() => { setDoc(null); setVersions([]); }}>New</button>
        <span style={{ marginLeft: 'auto', color: busy ? C.accent : C.dim, fontSize: 11 }}>
          {busy || `v${versions.length} · ${doc.sections.length} sections`}
        </span>
      </div>

      {error && (
        <div style={{ background: C.redBg, borderBottom: `1px solid ${C.border}`, padding: '6px 20px', fontSize: 11, color: C.red }}>
          {error}
        </div>
      )}

      {/* ── Scrollable content ───────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 16px' }}>
        <div>

          {doc.sections.map((s, i) => {
            const draft     = drafts[s.id] ?? s.content;
            const isDirty   = draft !== s.content;
            const isBusy    = sectionBusy[s.id] ?? false;
            const isFlashed = flashed[s.id] ?? false;

            return (
              <div
                key={s.id}
                style={{
                  marginBottom: 20,
                  background: C.surface,
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  overflow: 'hidden',
                }}
              >
                {/* Card header */}
                <div style={{ padding: '10px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{
                    fontSize: 11, color: C.dim, letterSpacing: '0.07em',
                    background: C.elevated, border: `1px solid ${C.border}`,
                    borderRadius: 3, padding: '2px 8px', flexShrink: 0,
                  }}>
                    §{i + 1} · {s.kind.toUpperCase()}
                  </span>
                  <span style={{ fontSize: 15, fontWeight: 600, color: C.txt }}>{s.title}</span>
                  {s.rationale && (
                    <span style={{ fontSize: 13, color: C.muted, fontStyle: 'italic', lineHeight: 1.5 }}>{s.rationale}</span>
                  )}
                </div>

                {/* Card body: left content + right suggestion */}
                <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr' }}>

                  {/* Left: editable textarea */}
                  <div style={{ padding: '12px 16px', borderRight: `1px solid ${C.border}` }}>
                    <p style={label}>Content</p>
                    <textarea
                      style={{
                        ...textarea,
                        minHeight: 340,
                        borderColor: isFlashed ? C.green : isDirty ? C.accent + '99' : C.border,
                        transition: 'border-color 400ms',
                      }}
                      value={draft}
                      onChange={e => setDrafts(prev => ({ ...prev, [s.id]: e.target.value }))}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                          e.preventDefault();
                          handleSaveSection(s.id, doc, drafts, versions);
                        }
                      }}
                    />
                    {isDirty && (
                      <div style={{ display: 'flex', gap: 6, marginTop: 8, alignItems: 'center' }}>
                        <button
                          style={{ ...btn(true), padding: '4px 12px' }}
                          onClick={() => handleSaveSection(s.id, doc, drafts, versions)}
                        >
                          Save
                        </button>
                        <span style={{ fontSize: 11, color: C.dim }}>or ⌘↵</span>
                        <button
                          style={{ ...btn(), marginLeft: 6 }}
                          onClick={() => setDrafts(prev => ({ ...prev, [s.id]: s.content }))}
                        >
                          Discard
                        </button>
                      </div>
                    )}
                    {s.history.length > 0 && !isDirty && (
                      <p style={{ fontSize: 11, color: C.dim, marginTop: 8 }}>
                        {s.history.length} edit{s.history.length > 1 ? 's' : ''}
                      </p>
                    )}
                  </div>

                  {/* Right: LLM suggestion */}
                  <div style={{ padding: '12px 16px', background: C.bg }}>
                    <p style={label}>Suggest a change</p>
                    <textarea
                      style={{ ...textarea, minHeight: 200 }}
                      value={suggestions[s.id] ?? ''}
                      onChange={e => setSuggestions(prev => ({ ...prev, [s.id]: e.target.value }))}
                      placeholder="Describe what to improve in this section…"
                      onKeyDown={e => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          if (!isBusy && suggestions[s.id]?.trim()) {
                            handleApplySuggestion(s.id);
                          }
                        }
                      }}
                    />
                    <button
                      style={{ ...btn(false), marginTop: 8, width: '100%', padding: '5px 10px', opacity: (isBusy || !suggestions[s.id]?.trim()) ? 0.5 : 1 }}
                      onClick={() => handleApplySuggestion(s.id)}
                      disabled={isBusy || !suggestions[s.id]?.trim()}
                    >
                      {isBusy ? 'Applying…' : 'Apply  ↵'}
                    </button>
                    <p style={{ fontSize: 11, color: C.dim, marginTop: 8, lineHeight: 1.5 }}>
                      Enter a suggestion — the AI rewrites this section and updates it.
                      <br />Press ↵ to apply, Shift+↵ for newline.
                    </p>
                  </div>

                </div>
              </div>
            );
          })}

          {/* Stitch & copy */}
          <div style={{ display: 'flex', justifyContent: 'center', padding: '20px 0 40px' }}>
            <button
              style={{
                ...btn(stitched),
                padding: '9px 28px',
                fontSize: 13,
                letterSpacing: '-0.01em',
              }}
              onClick={handleStitch}
            >
              {stitched ? 'Copied ✓' : `Stitch all ${doc.sections.length} sections → copy`}
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
