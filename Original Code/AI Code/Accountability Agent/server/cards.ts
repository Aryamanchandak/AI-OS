import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { cardsSchema, type PrincipleCard } from './schema.js';

let cachedCards: PrincipleCard[] | undefined;

export function loadCards(): PrincipleCard[] {
  if (cachedCards) return cachedCards;

  const path = resolve(process.cwd(), 'data/cards.json');
  const raw = JSON.parse(readFileSync(path, 'utf8')) as unknown;
  cachedCards = cardsSchema.parse(raw);
  return cachedCards;
}

export type RankedCard = {
  card: PrincipleCard;
  score: number;
  matchedCues: string[];
  personalWeight: number;
};

export type CardPerformance = { resolved: number; hits: number };

export function personalWeight(performance?: CardPerformance): number {
  if (!performance) return 0.5;
  return (performance.hits + 1) / (performance.resolved + 2);
}

export function rankCards(
  cards: PrincipleCard[],
  features: string[],
  performance: Record<string, CardPerformance> = {},
  minimumCueScore = 0.2,
): RankedCard[] {
  const featureSet = new Set(features);

  return cards
    .filter((card) => card.replication !== 'dead')
    .map((card) => {
      const matchedCues = card.cues.filter((cue) => featureSet.has(cue));
      return {
        card,
        matchedCues,
        personalWeight: personalWeight(performance[card.id]),
        score: (matchedCues.length / card.cues.length) * (0.6 + 0.4 * personalWeight(performance[card.id])),
      };
    })
    .filter(({ matchedCues, card }) => matchedCues.length / card.cues.length >= minimumCueScore)
    .sort((a, b) => b.score - a.score || b.matchedCues.length - a.matchedCues.length || a.card.id.localeCompare(b.card.id));
}
