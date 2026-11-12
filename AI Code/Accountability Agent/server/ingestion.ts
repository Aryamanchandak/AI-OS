import { randomUUID } from 'node:crypto';
import type { InferenceGateway } from './gateway.js';
import { ingestionJsonSchema } from './json-schemas.js';
import { CUE_TAXONOMY, ingestionPrompt } from './prompts.js';
import { ingestedCardsSchema, type PrincipleCard } from './schema.js';
import type { Passage, PraxisStore } from './store.js';
import type { PassageStore } from './passages.js';

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
}

function chunks(text: string, size = 1200): string[] {
  const paragraphs = text.split(/\n\s*\n/).map((item) => item.trim()).filter(Boolean);
  const result: string[] = [];
  let current = '';
  for (const paragraph of paragraphs) {
    if (paragraph.length > size) {
      if (current) { result.push(current); current = ''; }
      for (let offset = 0; offset < paragraph.length; offset += size) result.push(paragraph.slice(offset, offset + size));
      continue;
    }
    if (current && current.length + paragraph.length > size) {
      result.push(current);
      current = paragraph;
    } else {
      current = current ? `${current}\n\n${paragraph}` : paragraph;
    }
  }
  if (current) result.push(current);
  return result;
}

export class IngestionService {
  constructor(
    private readonly gateway: InferenceGateway,
    private readonly store: PraxisStore,
    private readonly passageStore: PassageStore,
  ) {}

  async ingest(title: string, author: string, sourceText: string): Promise<{ cards: PrincipleCard[]; passageCount: number }> {
    const extractedCards: Array<PrincipleCard & { id: string }> = [];
    for (const [index, sourceChunk] of chunks(sourceText, 50_000).entries()) {
      const extracted = await this.gateway.generateJson({
        name: `praxis_ingestion_${index + 1}`, prompt: ingestionPrompt(title, author, sourceChunk),
        schema: ingestionJsonSchema, parser: ingestedCardsSchema,
      });
      extractedCards.push(...extracted.cards);
    }
    const allowed = new Set<string>(CUE_TAXONOMY);
    const prefix = slug(title);
    const seenClaims = new Set<string>();
    const cards = extractedCards.map((card, index) => ({
      ...card,
      id: `${prefix}-${slug(card.id) || index + 1}-${randomUUID().slice(0, 6)}`,
      cues: card.cues.filter((cue) => allowed.has(cue)),
      source: `${author}, ${title} — ${card.source}`,
    })).filter((card) => {
      const key = card.claim.toLowerCase().replace(/\W+/g, ' ').trim();
      if (!card.cues.length || seenClaims.has(key)) return false;
      seenClaims.add(key);
      return true;
    });
    if (!cards.length) throw new Error('Extraction produced no cards with valid situational cues.');

    const passages: Passage[] = chunks(sourceText).map((text) => ({ id: randomUUID(), source: `${author}, ${title}`, text }));
    this.store.addIngestion(cards, passages);
    await this.passageStore.index(passages);
    return { cards, passageCount: passages.length };
  }
}
