import { fsrs, Rating, State, type Card as FsrsCard } from 'ts-fsrs'
import type { Flashcard } from '../types'

export const scheduler = fsrs({ request_retention: 0.9, enable_fuzz: true })

export const ratingOptions = [
  { rating: Rating.Again, label: 'Again', gesture: 'left' },
  { rating: Rating.Hard, label: 'Hard', gesture: 'down' },
  { rating: Rating.Good, label: 'Good', gesture: 'right' },
  { rating: Rating.Easy, label: 'Easy', gesture: 'up' }
] as const

export function dueCards(cards: Flashcard[], at = new Date()): Flashcard[] {
  return [...cards]
    .filter((card) => new Date(card.srs.due).getTime() <= at.getTime())
    .sort((a, b) => new Date(a.srs.due).getTime() - new Date(b.srs.due).getTime())
}

export function intervalLabel(due: Date, now = new Date()): string {
  const minutes = Math.max(1, Math.round((due.getTime() - now.getTime()) / 60_000))
  if (minutes < 60) return `${minutes}m`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d`
  const months = Math.round(days / 30)
  return `${months}mo`
}

export function previews(card: Flashcard, now = new Date()) {
  const result = scheduler.repeat(normalizeSrs(card.srs), now)
  return ratingOptions.map((option) => ({ ...option, result: result[option.rating], interval: intervalLabel(result[option.rating].card.due, now) }))
}

export function normalizeSrs(srs: FsrsCard): FsrsCard {
  return {
    ...srs,
    due: new Date(srs.due),
    last_review: srs.last_review ? new Date(srs.last_review) : undefined
  }
}

export function stateLabel(state: State): 'new' | 'learning' | 'review' {
  if (state === State.New) return 'new'
  if (state === State.Review) return 'review'
  return 'learning'
}
