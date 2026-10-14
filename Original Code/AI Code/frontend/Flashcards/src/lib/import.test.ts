import { describe, expect, it } from 'vitest'
import { generateLocalDrafts, parseCardJson, promptForUnit } from './import'

describe('card imports', () => {
  it('accepts both arrays and cards envelopes', () => {
    expect(parseCardJson('[{"term":"Haus","gloss":"house"}]')).toHaveLength(1)
    expect(parseCardJson('{"cards":[{"term":"Tür","gloss":"door"}]}')[0].term).toBe('Tür')
  })

  it('rejects malformed JSON and unsupported shapes', () => {
    expect(() => parseCardJson('{broken')).toThrow('not valid JSON')
    expect(() => parseCardJson('{"items":[]}')).toThrow('cards')
  })

  it('creates editable keyless drafts deterministically', () => {
    const first = generateLocalDrafts('Kapitel 5')
    const second = generateLocalDrafts('Kapitel 5')
    expect(first).toEqual(second)
    expect(first.length).toBeGreaterThan(4)
    expect(first.every((card) => card.term && card.gloss && card.unit === 'Kapitel 5')).toBe(true)
  })

  it('builds a constrained German generation prompt', () => {
    expect(promptForUnit('Reisen')).toContain('German flashcards')
    expect(promptForUnit('Reisen')).toContain('Reisen')
  })
})
