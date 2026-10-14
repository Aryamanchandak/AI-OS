import type { Card as FsrsCard, Rating, State } from 'ts-fsrs'

export type Article = 'der' | 'die' | 'das' | null
export type Screen = 'decks' | 'session' | 'detail' | 'stats' | 'import'

export interface Deck {
  id: string
  name: string
  description: string
  source: string
  createdAt: Date
  updatedAt: Date
  color: string
}

export interface Flashcard {
  id: string
  deckId: string
  unit: string
  term: string
  article: Article
  plural: string
  ipa: string
  gloss: string
  exampleDe: string
  exampleEn: string
  note: string
  tags: string[]
  audioUrl?: string
  imageUrl?: string
  createdAt: Date
  updatedAt: Date
  srs: FsrsCard
}

export interface ReviewRecord {
  id?: number
  cardId: string
  deckId: string
  rating: Rating
  reviewedAt: Date
  dueBefore: Date
  dueAfter: Date
  scheduledDays: number
  stateBefore: State
}

export interface ImportCard {
  term: string
  article?: Article
  plural?: string
  ipa?: string
  gloss: string
  example_de?: string
  example_en?: string
  note?: string
  tags?: string[]
  unit?: string
}

export interface DeckWithCounts extends Deck {
  total: number
  due: number
  newCount: number
  learning: number
}
