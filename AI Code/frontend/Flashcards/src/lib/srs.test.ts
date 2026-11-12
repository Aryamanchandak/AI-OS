import { describe, expect, it } from 'vitest'
import { createEmptyCard, Rating, State } from 'ts-fsrs'
import { dueCards, intervalLabel, previews, stateLabel } from './srs'
import type { Flashcard } from '../types'

function card(id: string, due: Date): Flashcard {
  return {
    id, deckId: 'deck', unit: 'Unit', term: id, article: null, plural: '', ipa: '', gloss: id,
    exampleDe: '', exampleEn: '', note: '', tags: [], createdAt: new Date(0), updatedAt: new Date(0),
    srs: { ...createEmptyCard(due), due }
  }
}

describe('SRS helpers', () => {
  it('filters and orders due cards', () => {
    const now = new Date('2026-01-02T12:00:00Z')
    const result = dueCards([card('future', new Date('2026-01-03')), card('older', new Date('2026-01-01')), card('newer', new Date('2026-01-02'))], now)
    expect(result.map((item) => item.id)).toEqual(['older', 'newer'])
  })

  it('formats useful interval units', () => {
    const now = new Date('2026-01-01T00:00:00Z')
    expect(intervalLabel(new Date('2026-01-01T00:10:00Z'), now)).toBe('10m')
    expect(intervalLabel(new Date('2026-01-05T00:00:00Z'), now)).toBe('4d')
  })

  it('provides all four FSRS grade previews', () => {
    const output = previews(card('Haus', new Date()))
    expect(output.map((item) => item.rating)).toEqual([Rating.Again, Rating.Hard, Rating.Good, Rating.Easy])
    expect(output.every((item) => item.result.card.due instanceof Date)).toBe(true)
  })

  it('groups relearning with learning', () => {
    expect(stateLabel(State.New)).toBe('new')
    expect(stateLabel(State.Relearning)).toBe('learning')
    expect(stateLabel(State.Review)).toBe('review')
  })
})
