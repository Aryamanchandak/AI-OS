import { motion, useReducedMotion, type PanInfo } from 'framer-motion'
import { Headphones, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import type { Flashcard } from '../types'

interface StudyCardProps {
  card: Flashcard
  revealed: boolean
  onReveal: () => void
  onGesture: (direction: 'left' | 'right' | 'up' | 'down') => void
  onOpenDetail: () => void
}

const articleLabels = { der: 'masculine', die: 'feminine', das: 'neuter' }

export function StudyCard({ card, revealed, onReveal, onGesture, onOpenDetail }: StudyCardProps) {
  const reduceMotion = useReducedMotion()
  const [speaking, setSpeaking] = useState(false)
  const [dragTarget, setDragTarget] = useState<'left' | 'right' | 'up' | 'down' | null>(null)
  const [dragStrength, setDragStrength] = useState(0)
  const termSize = useMemo(() => card.term.length > 23 ? 'term compact' : card.term.length > 16 ? 'term medium' : 'term', [card.term])

  useEffect(() => {
    return () => window.speechSynthesis?.cancel()
  }, [card.id])

  const speak = (event: React.MouseEvent) => {
    event.stopPropagation()
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(`${card.article || ''} ${card.term}. ${card.exampleDe}`)
    utterance.lang = 'de-DE'
    utterance.rate = 0.86
    utterance.onstart = () => setSpeaking(true)
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(utterance)
  }

  const finishDrag = (_: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
    const { x, y } = info.offset
    const threshold = 105
    setDragTarget(null)
    setDragStrength(0)
    if (Math.max(Math.abs(x), Math.abs(y)) < threshold) return
    if (Math.abs(x) > Math.abs(y)) onGesture(x > 0 ? 'right' : 'left')
    else onGesture(y > 0 ? 'down' : 'up')
  }

  const trackDrag = (_: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
    const { x, y } = info.offset
    const distance = Math.max(Math.abs(x), Math.abs(y))
    setDragStrength(Math.min(1, distance / 120))
    if (distance < 12) return setDragTarget(null)
    setDragTarget(Math.abs(x) > Math.abs(y) ? (x > 0 ? 'right' : 'left') : (y > 0 ? 'down' : 'up'))
  }

  return (
    <motion.div
      className={`study-card-wrap article-${card.article || 'none'}`}
      drag={revealed && !reduceMotion}
      dragSnapToOrigin
      dragElastic={0.16}
      dragConstraints={{ left: 0, right: 0, top: 0, bottom: 0 }}
      onDrag={trackDrag}
      onDragEnd={finishDrag}
      whileDrag={{ boxShadow: '0 28px 90px rgba(0,0,0,.55)' }}
      initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: .94, y: 8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: .96, y: -8 }}
      transition={{ duration: .26, ease: [0.2, 0.8, 0.2, 1] }}
    >
      <div className="study-card" onClick={onReveal}>
        <div className={`card-inner ${revealed ? 'revealed' : ''} ${reduceMotion ? 'reduced' : ''}`}>
          <div className="card-face card-front">
            <div className="card-topline">
              <span>{card.unit}</span>
              <button className={`icon-button ${speaking ? 'speaking' : ''}`} onClick={speak} aria-label={`Hear ${card.term} pronounced`}><Headphones size={19} /></button>
            </div>
            <div className="term-block" lang="de">
              {card.article && <span className="article" aria-label={articleLabels[card.article]}>{card.article}</span>}
              <h1 className={termSize}>{card.term}</h1>
              {(card.plural || card.ipa) && <p className="word-meta">{card.plural && `die ${card.plural}`}{card.plural && card.ipa && ' · '}{card.ipa}</p>}
            </div>
            <span className="reveal-hint"><RotateCcw size={14} /> Tap to reveal</span>
          </div>

          <div className="card-face card-back">
            <div className="card-topline">
              <span>{card.unit}</span>
              <button className={`icon-button ${speaking ? 'speaking' : ''}`} onClick={speak} aria-label="Play German text"><Headphones size={19} /></button>
            </div>
            <div className="answer-block">
              <p className="gloss">{card.gloss}</p>
              {card.exampleDe && <p className="example-de" lang="de">{card.exampleDe}</p>}
              {card.exampleEn && <p className="example-en">{card.exampleEn}</p>}
              {card.note && <p className="note">{card.note}</p>}
            </div>
            <button className="text-button detail-link" onClick={(event) => { event.stopPropagation(); onOpenDetail() }}>Card details</button>
          </div>
        </div>
      </div>
      {revealed && <div className={`drag-targets target-${dragTarget || 'none'}`} style={{ '--drag-strength': dragStrength } as CSSProperties} aria-hidden="true"><span className="target left">Again</span><span className="target right">Good</span><span className="target up">Easy</span><span className="target down">Hard</span></div>}
      {revealed && <div className="gesture-legend" aria-hidden="true"><span>← Again</span><span>↓ Hard</span><span>Good →</span><span>Easy ↑</span></div>}
    </motion.div>
  )
}
