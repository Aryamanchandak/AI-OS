import Dexie, { type EntityTable } from 'dexie'
import { createEmptyCard } from 'ts-fsrs'
import { seedCards } from './seed'
import type { Deck, Flashcard, ImportCard, ReviewRecord } from '../types'

class WortenDatabase extends Dexie {
  decks!: EntityTable<Deck, 'id'>
  cards!: EntityTable<Flashcard, 'id'>
  reviews!: EntityTable<ReviewRecord, 'id'>

  constructor() {
    super('worten')
    this.version(1).stores({
      decks: 'id, updatedAt',
      cards: 'id, deckId, [deckId+srs.due], srs.due, srs.state, updatedAt',
      reviews: '++id, cardId, deckId, reviewedAt, rating'
    })
  }
}

export const db = new WortenDatabase()

const id = () => crypto.randomUUID()

export async function cardsFromImport(deckId: string, cards: ImportCard[]): Promise<Flashcard[]> {
  const now = new Date()
  return cards.map((card) => ({
    id: id(),
    deckId,
    unit: card.unit || 'Imported vocabulary',
    term: card.term.trim(),
    article: card.article || null,
    plural: card.plural?.trim() || '',
    ipa: card.ipa?.trim() || '',
    gloss: card.gloss.trim(),
    exampleDe: card.example_de?.trim() || '',
    exampleEn: card.example_en?.trim() || '',
    note: card.note?.trim() || '',
    tags: card.tags?.filter(Boolean) || [],
    createdAt: now,
    updatedAt: now,
    srs: createEmptyCard(now)
  }))
}

export async function ensureSeedData(): Promise<void> {
  if ((await db.decks.count()) > 0) return
  const now = new Date()
  const deck: Deck = {
    id: 'netzwerk-a1-kap-4',
    name: 'Zu Hause',
    description: 'Rooms, neighbours and the small rituals of home.',
    source: 'Netzwerk neu A1 · Kapitel 4',
    createdAt: now,
    updatedAt: now,
    color: '#d59c68'
  }
  await db.transaction('rw', db.decks, db.cards, async () => {
    await db.decks.add(deck)
    await db.cards.bulkAdd(await cardsFromImport(deck.id, seedCards))
  })
}

export async function createDeck(name: string, description: string, source = 'Personal deck'): Promise<Deck> {
  const now = new Date()
  const deck: Deck = { id: id(), name: name.trim(), description: description.trim(), source, createdAt: now, updatedAt: now, color: '#d59c68' }
  await db.decks.add(deck)
  return deck
}

export async function importIntoDeck(deckId: string, cards: ImportCard[]): Promise<number> {
  const valid = cards.filter((card) => card.term?.trim() && card.gloss?.trim())
  if (!valid.length) throw new Error('No valid cards found. Each card needs a term and gloss.')
  await db.cards.bulkAdd(await cardsFromImport(deckId, valid))
  await db.decks.update(deckId, { updatedAt: new Date() })
  return valid.length
}

export async function deleteDeck(deckId: string): Promise<void> {
  await db.transaction('rw', db.decks, db.cards, db.reviews, async () => {
    await db.cards.where('deckId').equals(deckId).delete()
    await db.reviews.where('deckId').equals(deckId).delete()
    await db.decks.delete(deckId)
  })
}
