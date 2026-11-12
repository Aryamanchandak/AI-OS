import { describe, expect, it } from 'vitest';
import { loadCards, personalWeight, rankCards } from './cards.js';
import type { PrincipleCard } from './schema.js';

describe('principle-card ranking', () => {
  it('loads the complete curated v0 corpus', () => {
    const cards = loadCards();
    expect(cards).toHaveLength(15);
    expect(new Set(cards.map((card) => card.id)).size).toBe(15);
  });

  it('ranks situational cue overlap and applies personal demotion', () => {
    const ranked = rankCards(loadCards(), ['negotiation', 'you_move_first', 'one_shot', 'trust_not_low'], {
      'influence-001': { resolved: 8, hits: 0 },
      'gty-002': { resolved: 8, hits: 8 },
    });
    expect(ranked.length).toBeGreaterThan(0);
    expect(ranked.find((item) => item.card.id === 'influence-001')?.personalWeight).toBeCloseTo(0.1);
    expect(personalWeight({ resolved: 8, hits: 8 })).toBeCloseTo(0.9);
  });

  it('retains but never recommends dead cards', () => {
    const dead: PrincipleCard = {
      ...loadCards()[0], id: 'dead-001', replication: 'dead', cues: ['negotiation'],
    };
    expect(rankCards([dead], ['negotiation'])).toEqual([]);
  });
});
