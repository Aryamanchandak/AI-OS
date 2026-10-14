import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { AlertTriangle, ArrowLeft, BookOpen, Check, ChevronRight, CloudOff, Download, MoreHorizontal, Pencil, Plus, RefreshCw, Sparkles, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Rating, State } from 'ts-fsrs'
import { EmptyState } from './components/EmptyState'
import { Navigation } from './components/Navigation'
import { StudyCard } from './components/StudyCard'
import { createDeck, db, deleteDeck, ensureSeedData, importIntoDeck } from './data/db'
import { generateCards, generateLocalDrafts, parseCardJson } from './lib/import'
import { dueCards, previews, scheduler, stateLabel } from './lib/srs'
import type { Deck, DeckWithCounts, Flashcard, ImportCard, ReviewRecord, Screen } from './types'

const dateFormatter = new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' })

function App() {
  const [screen, setScreen] = useState<Screen>('decks')
  const [decks, setDecks] = useState<Deck[]>([])
  const [cards, setCards] = useState<Flashcard[]>([])
  const [reviews, setReviews] = useState<ReviewRecord[]>([])
  const [selectedDeckId, setSelectedDeckId] = useState('')
  const [selectedCardId, setSelectedCardId] = useState('')
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState('')
  const [online, setOnline] = useState(navigator.onLine)

  const refresh = useCallback(async () => {
    try {
      const [nextDecks, nextCards, nextReviews] = await Promise.all([db.decks.toArray(), db.cards.toArray(), db.reviews.toArray()])
      setDecks(nextDecks)
      setCards(nextCards)
      setReviews(nextReviews)
      setSelectedDeckId((current) => current || nextDecks[0]?.id || '')
      setStatus('ready')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Local data could not be opened.')
      setStatus('error')
    }
  }, [])

  useEffect(() => {
    ensureSeedData().then(refresh).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : 'Setup failed.')
      setStatus('error')
    })
  }, [refresh])

  useEffect(() => {
    const goOnline = () => setOnline(true)
    const goOffline = () => setOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => { window.removeEventListener('online', goOnline); window.removeEventListener('offline', goOffline) }
  }, [])

  const deckCounts = useMemo<DeckWithCounts[]>(() => decks.map((deck) => {
    const deckCards = cards.filter((card) => card.deckId === deck.id)
    return {
      ...deck,
      total: deckCards.length,
      due: dueCards(deckCards).length,
      newCount: deckCards.filter((card) => card.srs.state === State.New).length,
      learning: deckCards.filter((card) => card.srs.state === State.Learning || card.srs.state === State.Relearning).length
    }
  }), [cards, decks])

  const navigate = (target: Screen) => {
    setScreen(target)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const startDeck = (deckId: string) => {
    setSelectedDeckId(deckId)
    navigate('session')
  }

  const openDetail = (cardId: string) => {
    setSelectedCardId(cardId)
    navigate('detail')
  }

  if (status === 'loading') return <LoadingScreen />
  if (status === 'error') return <ErrorScreen message={error} onRetry={() => { setStatus('loading'); void refresh() }} />

  return (
    <div className="app-shell">
      {!online && <div className="offline-banner"><CloudOff size={15} /> Offline · your decks and reviews still work</div>}
      <header className="topbar">
        <button className="brand" onClick={() => navigate('decks')} aria-label="Wörten home"><span>W</span>Wörten</button>
        <p>{deckCounts.reduce((sum, deck) => sum + deck.due, 0)} due today</p>
      </header>

      <main className={screen === 'session' ? 'main study-main' : 'main'}>
        <AnimatePresence mode="wait">
          {screen === 'decks' && <DecksScreen key="decks" decks={deckCounts} onStart={startDeck} onAdd={() => navigate('import')} onDelete={async (id) => { await deleteDeck(id); await refresh() }} onUpdated={refresh} />}
          {screen === 'session' && <SessionScreen key={`session-${selectedDeckId}`} deck={decks.find((deck) => deck.id === selectedDeckId)} cards={cards.filter((card) => card.deckId === selectedDeckId)} onRefresh={refresh} onOpenDetail={openDetail} onStop={() => navigate('decks')} />}
          {screen === 'detail' && <DetailScreen key="detail" card={cards.find((card) => card.id === selectedCardId)} onBack={() => navigate('decks')} onSaved={refresh} />}
          {screen === 'stats' && <StatsScreen key="stats" cards={cards} reviews={reviews} decks={decks} onStudy={() => navigate('decks')} />}
          {screen === 'import' && <ImportScreen key="import" decks={decks} selectedDeckId={selectedDeckId} onComplete={async (deckId) => { setSelectedDeckId(deckId); await refresh(); navigate('decks') }} />}
        </AnimatePresence>
      </main>
      {screen !== 'session' && <Navigation screen={screen} onNavigate={navigate} />}
    </div>
  )
}

function LoadingScreen() {
  return <div className="center-state"><span className="brand-mark">W</span><p>Opening your library…</p></div>
}

function ErrorScreen({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="center-state"><AlertTriangle size={34} /><h1>Something got tangled.</h1><p>{message}</p><button className="primary-button" onClick={onRetry}>Try again</button></div>
}

interface DecksScreenProps {
  decks: DeckWithCounts[]
  onStart: (id: string) => void
  onAdd: () => void
  onDelete: (id: string) => Promise<void>
  onUpdated: () => Promise<void>
}

function DecksScreen({ decks, onStart, onAdd, onDelete, onUpdated }: DecksScreenProps) {
  const [menu, setMenu] = useState('')
  const [editing, setEditing] = useState<DeckWithCounts | null>(null)
  if (!decks.length) return <EmptyState Icon={BookOpen} eyebrow="First run" title="Your first word starts here." message="Create a deck or import vocabulary from your current German unit." action="Create a deck" onAction={onAdd} />
  return (
    <motion.section className="page decks-page" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <div className="page-heading split-heading">
        <div><p className="eyebrow">Your library</p><h1>Pick up where<br />you left off.</h1></div>
        <button className="round-button" onClick={onAdd} aria-label="Add deck"><Plus size={23} /></button>
      </div>
      <div className="deck-grid">
        {decks.map((deck, index) => (
          <motion.article className="deck-card" key={deck.id} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .05 }}>
            <div className="deck-card-top">
              <span className="deck-index">{String(index + 1).padStart(2, '0')}</span>
              <div className="menu-wrap">
                <button className="icon-button" onClick={() => setMenu(menu === deck.id ? '' : deck.id)} aria-label={`More options for ${deck.name}`}><MoreHorizontal size={20} /></button>
                {menu === deck.id && <div className="popover"><button className="neutral" onClick={() => { setEditing(deck); setMenu('') }}><Pencil size={15} /> Edit deck</button><button onClick={() => { if (window.confirm(`Delete “${deck.name}” and all its review history?`)) void onDelete(deck.id) }}><Trash2 size={15} /> Delete deck</button></div>}
              </div>
            </div>
            <div>
              <p className="deck-source">{deck.source}</p>
              <h2>{deck.name}</h2>
              <p className="muted">{deck.description}</p>
            </div>
            <div className="deck-meta"><span><strong>{deck.due}</strong> due</span><span><strong>{deck.total}</strong> cards</span><span><strong>{deck.newCount}</strong> new</span></div>
            <button className="deck-action" onClick={() => onStart(deck.id)} disabled={!deck.total}>
              <span>{deck.due ? 'Begin session' : deck.total ? 'Nothing due' : 'Empty deck'}</span><ChevronRight size={20} />
            </button>
          </motion.article>
        ))}
      </div>
      {editing && <div className="modal-backdrop" role="presentation" onMouseDown={() => setEditing(null)}><div className="modal" role="dialog" aria-modal="true" aria-labelledby="edit-deck-title" onMouseDown={(event) => event.stopPropagation()}><p className="eyebrow">Deck settings</p><h2 id="edit-deck-title">Edit {editing.name}</h2><div className="form-stack"><label>Name<input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} autoFocus /></label><label>Description<textarea value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></label><label>Source<input value={editing.source} onChange={(e) => setEditing({ ...editing, source: e.target.value })} /></label><div className="button-row"><button className="secondary-button" onClick={() => setEditing(null)}>Cancel</button><button className="primary-button" disabled={!editing.name.trim()} onClick={async () => { await db.decks.update(editing.id, { name: editing.name.trim(), description: editing.description.trim(), source: editing.source.trim(), updatedAt: new Date() }); await onUpdated(); setEditing(null) }}>Save deck</button></div></div></div></div>}
    </motion.section>
  )
}

interface SessionProps {
  deck?: Deck
  cards: Flashcard[]
  onRefresh: () => Promise<void>
  onOpenDetail: (id: string) => void
  onStop: () => void
}

function SessionScreen({ deck, cards, onRefresh, onOpenDetail, onStop }: SessionProps) {
  const [queue] = useState(() => dueCards(cards))
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [graded, setGraded] = useState<Rating[]>([])
  const [busy, setBusy] = useState(false)
  const reduceMotion = useReducedMotion()
  const card = queue[index]
  const initialSegments = useRef(queue.reduce((acc, item) => { acc[stateLabel(item.srs.state)] += 1; return acc }, { new: 0, learning: 0, review: 0 }))
  const preview = useMemo(() => card ? previews(card) : [], [card])
  const sessionDone = queue.length > 0 && index >= queue.length

  const grade = async (rating: Rating.Again | Rating.Hard | Rating.Good | Rating.Easy) => {
    if (!card || !revealed || busy) return
    setBusy(true)
    const now = new Date()
    const next = scheduler.repeat(card.srs, now)[rating]
    await db.transaction('rw', db.cards, db.reviews, async () => {
      await db.cards.update(card.id, { srs: next.card, updatedAt: now })
      await db.reviews.add({ cardId: card.id, deckId: card.deckId, rating, reviewedAt: now, dueBefore: new Date(card.srs.due), dueAfter: next.card.due, scheduledDays: next.card.scheduled_days, stateBefore: card.srs.state })
    })
    if ('vibrate' in navigator) navigator.vibrate(12)
    setGraded((current) => [...current, rating])
    setRevealed(false)
    setIndex((current) => current + 1)
    setBusy(false)
    void onRefresh()
  }

  const gesture = (direction: 'left' | 'right' | 'up' | 'down') => {
    const map: Record<'left' | 'right' | 'up' | 'down', Rating.Again | Rating.Hard | Rating.Good | Rating.Easy> = { left: Rating.Again, down: Rating.Hard, right: Rating.Good, up: Rating.Easy }
    void grade(map[direction])
  }

  if (!deck) return <EmptyState Icon={BookOpen} eyebrow="No deck selected" title="Choose what to study." message="Return to your decks and start a session." action="View decks" onAction={onStop} />
  if (!cards.length) return <EmptyState Icon={Plus} eyebrow="Deck empty" title="This deck needs words." message="Add or import a few cards before beginning a session." action="Stop session" onAction={onStop} />
  if (!queue.length) return <EmptyState Icon={Check} eyebrow="Nothing due" title="You’re caught up." message={`Your next ${deck.name} card will appear here when it is due.`} action="Stop for now" onAction={onStop} />
  if (sessionDone) {
    const retained = graded.filter((item) => item !== Rating.Again).length
    const retention = Math.round((retained / Math.max(1, graded.length)) * 100)
    return <section className="session-complete page-enter"><div className="completion-ring"><span>{retention}%</span><small>retained</small></div><p className="eyebrow">Session complete</p><h1>Leave the words<br />to settle.</h1><p className="muted">You reviewed {graded.length} {graded.length === 1 ? 'card' : 'cards'}. A clean stop protects tomorrow’s rhythm.</p><button className="primary-button" onClick={onStop}>Stop for now</button></section>
  }

  const remaining = queue.length - index
  const progress = (index / queue.length) * 100
  const totalSegments = Math.max(1, queue.length)
  return (
    <motion.section className="session" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="progress-track" aria-label={`${remaining} cards remaining`}>
        <span className="progress-done" style={{ width: `${progress}%` }} />
        <span className="progress-new" style={{ width: `${initialSegments.current.new / totalSegments * 100}%` }} />
        <span className="progress-learning" style={{ width: `${initialSegments.current.learning / totalSegments * 100}%` }} />
        <span className="progress-review" style={{ width: `${initialSegments.current.review / totalSegments * 100}%` }} />
      </div>
      <div className="session-header"><button className="text-button" onClick={onStop}><ArrowLeft size={17} /> Stop</button><span>{deck.name}</span><span className="session-dot" title={`${remaining} remaining`} /></div>
      <div className="card-stage">
        <AnimatePresence mode="wait">
          <StudyCard key={card.id} card={card} revealed={revealed} onReveal={() => setRevealed(true)} onGesture={gesture} onOpenDetail={() => onOpenDetail(card.id)} />
        </AnimatePresence>
      </div>
      <div className={`grade-row ${revealed ? 'visible' : ''}`} aria-hidden={!revealed}>
        {preview.map((option) => <button key={option.rating} disabled={!revealed || busy} onClick={() => void grade(option.rating)} aria-label={`${option.label}, next interval ${option.interval}`}><span>{option.label}</span><small>{option.interval}</small></button>)}
      </div>
      {!revealed && <button className="reveal-button" onClick={() => setRevealed(true)}>Show answer</button>}
      {reduceMotion && <span className="sr-only">Reduced motion is enabled. Card transitions use a crossfade.</span>}
    </motion.section>
  )
}

function DetailScreen({ card, onBack, onSaved }: { card?: Flashcard; onBack: () => void; onSaved: () => Promise<void> }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(card)
  if (!card || !draft) return <EmptyState Icon={BookOpen} eyebrow="Card missing" title="That card moved." message="It may have been removed from its deck." action="Back to decks" onAction={onBack} />

  const save = async () => {
    await db.cards.update(card.id, { ...draft, updatedAt: new Date() })
    await onSaved()
    setEditing(false)
  }
  const remove = async () => {
    if (!window.confirm(`Delete “${card.term}”?`)) return
    await db.cards.delete(card.id)
    await onSaved()
    onBack()
  }

  return (
    <motion.section className="page detail-page" initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
      <div className="detail-toolbar"><button className="text-button" onClick={onBack}><ArrowLeft size={17} /> Back</button><div><button className="icon-button" onClick={() => setEditing(!editing)} aria-label="Edit card"><Pencil size={18} /></button><button className="icon-button danger" onClick={() => void remove()} aria-label="Delete card"><Trash2 size={18} /></button></div></div>
      <div className={`detail-word article-${card.article || 'none'}`}><span>{card.article}</span><h1 lang="de">{card.term}</h1><p>{card.ipa}</p></div>
      {editing ? <CardEditor draft={draft} onChange={setDraft} onSave={() => void save()} onCancel={() => { setDraft(card); setEditing(false) }} /> : (
        <div className="detail-grid">
          <section><p className="eyebrow">Meaning</p><h2>{card.gloss}</h2>{card.plural && <p className="muted">Plural · die {card.plural}</p>}</section>
          <section><p className="eyebrow">In context</p><blockquote lang="de">{card.exampleDe || 'No example sentence yet.'}</blockquote><p className="muted">{card.exampleEn}</p></section>
          <section><p className="eyebrow">Memory</p><div className="memory-grid"><span><strong>{card.srs.reps}</strong> reviews</span><span><strong>{card.srs.lapses}</strong> lapses</span><span><strong>{card.srs.stability.toFixed(1)}</strong> stability</span><span><strong>{dateFormatter.format(new Date(card.srs.due))}</strong> due</span></div></section>
          {(card.note || card.tags.length > 0) && <section><p className="eyebrow">Notes</p><p>{card.note}</p><div className="tags">{card.tags.map((tag) => <span key={tag}>{tag}</span>)}</div></section>}
        </div>
      )}
    </motion.section>
  )
}

function CardEditor({ draft, onChange, onSave, onCancel }: { draft: Flashcard; onChange: (card: Flashcard) => void; onSave: () => void; onCancel: () => void }) {
  const field = (key: keyof Flashcard, value: string) => onChange({ ...draft, [key]: value })
  return <div className="form-stack editor-form"><div className="form-grid"><label>Article<select value={draft.article || ''} onChange={(e) => onChange({ ...draft, article: (e.target.value || null) as Flashcard['article'] })}><option value="">None</option><option>der</option><option>die</option><option>das</option></select></label><label>Term<input value={draft.term} onChange={(e) => field('term', e.target.value)} /></label><label>Plural<input value={draft.plural} onChange={(e) => field('plural', e.target.value)} /></label><label>IPA<input value={draft.ipa} onChange={(e) => field('ipa', e.target.value)} /></label></div><label>Meaning<input value={draft.gloss} onChange={(e) => field('gloss', e.target.value)} /></label><label>German example<textarea value={draft.exampleDe} onChange={(e) => field('exampleDe', e.target.value)} /></label><label>English example<textarea value={draft.exampleEn} onChange={(e) => field('exampleEn', e.target.value)} /></label><label>Note<textarea value={draft.note} onChange={(e) => field('note', e.target.value)} /></label><div className="button-row"><button className="secondary-button" onClick={onCancel}>Cancel</button><button className="primary-button" onClick={onSave} disabled={!draft.term.trim() || !draft.gloss.trim()}>Save card</button></div></div>
}

function StatsScreen({ cards, reviews, decks, onStudy }: { cards: Flashcard[]; reviews: ReviewRecord[]; decks: Deck[]; onStudy: () => void }) {
  const lastSeven = useMemo(() => Array.from({ length: 7 }, (_, index) => {
    const date = new Date(); date.setHours(0, 0, 0, 0); date.setDate(date.getDate() - (6 - index))
    const next = new Date(date); next.setDate(next.getDate() + 1)
    return { date, count: reviews.filter((review) => new Date(review.reviewedAt) >= date && new Date(review.reviewedAt) < next).length }
  }), [reviews])
  const max = Math.max(1, ...lastSeven.map((item) => item.count))
  const todayReviews = lastSeven[6].count
  const retained = reviews.length ? Math.round(reviews.filter((review) => review.rating !== Rating.Again).length / reviews.length * 100) : 0
  const mature = cards.filter((card) => card.srs.state === State.Review).length
  if (!reviews.length) return <EmptyState Icon={BookOpen} eyebrow="Stats" title="Your rhythm starts with one review." message="Study a few cards and your retention, streak and activity will appear here." action="Choose a deck" onAction={onStudy} />
  return (
    <motion.section className="page stats-page" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <div className="page-heading"><p className="eyebrow">Memory, measured gently</p><h1>Your practice<br />has a pulse.</h1></div>
      <div className="stat-hero"><div><span className="stat-number">{retained}%</span><p>retention across {reviews.length} reviews</p></div><div className="retention-orbit"><span>{mature}</span><small>mature</small></div></div>
      <section className="activity-panel"><div className="panel-heading"><div><p className="eyebrow">Last seven days</p><h2>{todayReviews} reviews today</h2></div><span>{decks.length} {decks.length === 1 ? 'deck' : 'decks'}</span></div><div className="bar-chart">{lastSeven.map((item) => <div className="bar-column" key={item.date.toISOString()}><div className="bar" style={{ height: `${Math.max(5, item.count / max * 100)}%` }}><span>{item.count}</span></div><small>{item.date.toLocaleDateString('en', { weekday: 'narrow' })}</small></div>)}</div></section>
      <div className="stat-grid"><article><span>{cards.length}</span><p>words in memory</p></article><article><span>{cards.filter((card) => new Date(card.srs.due) <= new Date()).length}</span><p>due now</p></article><article><span>{Math.round(cards.reduce((sum, card) => sum + card.srs.stability, 0) / Math.max(1, cards.length))}d</span><p>avg. stability</p></article></div>
    </motion.section>
  )
}

type ImportMode = 'manual' | 'json' | 'generate'
type DraftCard = ImportCard & { _draftId: string }

function ImportScreen({ decks, selectedDeckId, onComplete }: { decks: Deck[]; selectedDeckId: string; onComplete: (deckId: string) => Promise<void> }) {
  const [mode, setMode] = useState<ImportMode>('manual')
  const [deckId, setDeckId] = useState(selectedDeckId || decks[0]?.id || 'new')
  const [newDeck, setNewDeck] = useState({ name: '', description: '' })
  const [manual, setManual] = useState<ImportCard>({ term: '', article: null, gloss: '', plural: '', example_de: '', example_en: '', tags: [] })
  const [json, setJson] = useState('')
  const [unit, setUnit] = useState('Netzwerk neu A1 · Kapitel 5')
  const [drafts, setDrafts] = useState<DraftCard[]>([])
  const [advanced, setAdvanced] = useState(false)
  const [api, setApi] = useState({ endpoint: 'https://api.openai.com/v1/chat/completions', key: '', model: 'gpt-4.1-mini' })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const resolveDeck = async () => {
    if (deckId !== 'new') return deckId
    if (!newDeck.name.trim()) throw new Error('Give the new deck a name first.')
    return (await createDeck(newDeck.name, newDeck.description)).id
  }

  const saveCards = async (items: ImportCard[]) => {
    setBusy(true); setMessage('')
    try {
      const target = await resolveDeck()
      const count = await importIntoDeck(target, items)
      setMessage(`${count} ${count === 1 ? 'card' : 'cards'} added.`)
      await onComplete(target)
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : 'Import failed.') }
    finally { setBusy(false) }
  }

  const parseAndSave = () => {
    try { void saveCards(parseCardJson(json)) } catch (reason) { setMessage(reason instanceof Error ? reason.message : 'Import failed.') }
  }

  const createDrafts = async () => {
    setBusy(true); setMessage('')
    try {
      const generated = advanced && api.key ? await generateCards(api.endpoint, api.key, api.model, unit) : generateLocalDrafts(unit)
      setDrafts(generated.map((item) => ({ ...item, _draftId: crypto.randomUUID() })))
      setMessage('Drafts ready — edit anything before importing.')
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : 'Generation failed.') }
    finally { setBusy(false) }
  }

  const exportData = async () => {
    const data = { version: 1, exportedAt: new Date().toISOString(), decks: await db.decks.toArray(), cards: await db.cards.toArray(), reviews: await db.reviews.toArray() }
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `worten-backup-${new Date().toISOString().slice(0, 10)}.json`; anchor.click(); URL.revokeObjectURL(url)
  }

  const updateDraft = (draftId: string, key: keyof ImportCard, value: string) => setDrafts((current) => current.map((item) => item._draftId === draftId ? { ...item, [key]: value } : item))

  return (
    <motion.section className="page import-page" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <div className="page-heading"><p className="eyebrow">Add to memory</p><h1>Bring your<br />next words.</h1></div>
      <div className="import-layout"><div className="import-main">
        <div className="segmented-control">{(['manual', 'json', 'generate'] as ImportMode[]).map((item) => <button key={item} className={mode === item ? 'active' : ''} onClick={() => { setMode(item); setMessage('') }}>{item === 'json' ? 'JSON import' : item === 'generate' ? 'Smart drafts' : 'One card'}</button>)}</div>
        <div className="import-panel">
          {mode === 'manual' && <div className="form-stack"><div className="form-grid"><label>Article<select value={manual.article || ''} onChange={(e) => setManual({ ...manual, article: (e.target.value || null) as ImportCard['article'] })}><option value="">None</option><option>der</option><option>die</option><option>das</option></select></label><label>German term<input lang="de" value={manual.term} onChange={(e) => setManual({ ...manual, term: e.target.value })} placeholder="Schlüssel" /></label></div><label>English meaning<input value={manual.gloss} onChange={(e) => setManual({ ...manual, gloss: e.target.value })} placeholder="key" /></label><div className="form-grid"><label>Plural<input value={manual.plural} onChange={(e) => setManual({ ...manual, plural: e.target.value })} placeholder="Schlüssel" /></label><label>German example<input lang="de" value={manual.example_de} onChange={(e) => setManual({ ...manual, example_de: e.target.value })} /></label></div><button className="primary-button" disabled={busy || !manual.term.trim() || !manual.gloss.trim()} onClick={() => void saveCards([manual])}>Add card</button></div>}
          {mode === 'json' && <div className="form-stack"><p className="muted">Paste an array of cards. Required fields: <code>term</code> and <code>gloss</code>.</p><label>Card JSON<textarea className="code-input" value={json} onChange={(e) => setJson(e.target.value)} placeholder={'[{"term":"Bahnhof","article":"der","gloss":"train station"}]'} /></label><button className="primary-button" disabled={busy || !json.trim()} onClick={parseAndSave}><Upload size={17} /> Import cards</button></div>}
          {mode === 'generate' && <div className="form-stack"><div className="generator-intro"><Sparkles size={24} /><div><h2>Keyless smart drafts</h2><p className="muted">Start with editable, offline-friendly German cards. No account or API key needed.</p></div></div><label>Course unit or theme<input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="Netzwerk neu A1 · Kapitel 5" /></label><button className="primary-button" disabled={busy || !unit.trim()} onClick={() => void createDrafts()}>{busy ? <RefreshCw className="spin" size={17} /> : <Sparkles size={17} />} Generate editable drafts</button><button className="advanced-toggle" onClick={() => setAdvanced(!advanced)}>{advanced ? 'Hide' : 'Show'} optional model connection <ChevronRight size={15} /></button>{advanced && <div className="advanced-panel"><p>Your key stays in memory for this tab only.</p><label>Compatible endpoint<input value={api.endpoint} onChange={(e) => setApi({ ...api, endpoint: e.target.value })} /></label><div className="form-grid"><label>Model<input value={api.model} onChange={(e) => setApi({ ...api, model: e.target.value })} /></label><label>API key<input type="password" value={api.key} onChange={(e) => setApi({ ...api, key: e.target.value })} autoComplete="off" /></label></div></div>}{drafts.length > 0 && <div className="draft-list"><div className="draft-list-heading"><h3>{drafts.length} drafts</h3><span>Edit before import</span></div>{drafts.map((draft) => <article className="draft-card" key={draft._draftId}><div className="form-grid"><label>Term<input value={draft.term} onChange={(e) => updateDraft(draft._draftId, 'term', e.target.value)} /></label><label>Meaning<input value={draft.gloss} onChange={(e) => updateDraft(draft._draftId, 'gloss', e.target.value)} /></label></div><label>German example<input value={draft.example_de || ''} onChange={(e) => updateDraft(draft._draftId, 'example_de', e.target.value)} /></label><button className="icon-button draft-remove" onClick={() => setDrafts((current) => current.filter((item) => item._draftId !== draft._draftId))} aria-label={`Remove ${draft.term}`}><Trash2 size={16} /></button></article>)}<button className="primary-button" disabled={busy} onClick={() => void saveCards(drafts)}>Import {drafts.length} drafts</button></div>}</div>}
          {message && <p className={message.includes('failed') || message.includes('valid') || message.includes('name') ? 'form-message error' : 'form-message'}>{message}</p>}
        </div>
      </div><aside className="import-sidebar"><p className="eyebrow">Destination</p><label>Deck<select value={deckId} onChange={(e) => setDeckId(e.target.value)}>{decks.map((deck) => <option value={deck.id} key={deck.id}>{deck.name}</option>)}<option value="new">+ New deck</option></select></label>{deckId === 'new' && <div className="form-stack compact"><label>Deck name<input value={newDeck.name} onChange={(e) => setNewDeck({ ...newDeck, name: e.target.value })} placeholder="Travel basics" /></label><label>Description<textarea value={newDeck.description} onChange={(e) => setNewDeck({ ...newDeck, description: e.target.value })} /></label></div>}<div className="backup-box"><Download size={20} /><div><strong>Your data is yours.</strong><p>Keep a portable copy of decks and review history.</p></div><button className="secondary-button" onClick={() => void exportData()}>Export backup</button></div></aside></div>
    </motion.section>
  )
}

export default App
