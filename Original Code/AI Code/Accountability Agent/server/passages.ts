import type { Passage, PraxisStore } from './store.js';

export interface PassageStore {
  search(query: string, cardIds: string[], limit?: number): Promise<Passage[]>;
  index(passages: Passage[]): Promise<void>;
}

function terms(value: string): Set<string> {
  return new Set(value.toLowerCase().match(/[a-z]{4,}/g) ?? []);
}

export class LocalPassageStore implements PassageStore {
  constructor(private readonly store: PraxisStore) {}

  async search(query: string, cardIds: string[], limit = 3): Promise<Passage[]> {
    const queryTerms = terms(query);
    const ids = new Set(cardIds);
    return this.store.passages()
      .filter((passage) => !passage.cardId || ids.has(passage.cardId))
      .map((passage) => ({ passage, score: [...terms(passage.text)].filter((term) => queryTerms.has(term)).length }))
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit)
      .map(({ passage }) => passage);
  }

  async index(_passages: Passage[]): Promise<void> {
    // PraxisStore already persists local passages atomically.
  }
}

export class ChromaPassageStore implements PassageStore {
  constructor(private readonly url: string, private readonly fallback: PassageStore) {}

  async search(query: string, cardIds: string[], limit = 3): Promise<Passage[]> {
    try {
      const response = await fetch(`${this.url.replace(/\/$/, '')}/api/v1/collections/praxis_passages/query`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ query_texts: [query], n_results: limit, where: cardIds.length ? { cardId: { '$in': cardIds } } : undefined }),
      });
      if (!response.ok) throw new Error('Chroma unavailable.');
      const body = await response.json() as { ids?: string[][]; documents?: string[][]; metadatas?: Array<Array<Record<string, string>>> };
      return (body.documents?.[0] ?? []).map((text, index) => ({
        id: body.ids?.[0]?.[index] ?? `chroma-${index}`,
        text,
        source: body.metadatas?.[0]?.[index]?.source ?? 'Chroma passage',
        cardId: body.metadatas?.[0]?.[index]?.cardId,
      }));
    } catch {
      return this.fallback.search(query, cardIds, limit);
    }
  }

  async index(passages: Passage[]): Promise<void> {
    await this.fallback.index(passages);
    if (!passages.length) return;
    try {
      const response = await fetch(`${this.url.replace(/\/$/, '')}/api/v1/collections/praxis_passages/add`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          ids: passages.map(({ id }) => id), documents: passages.map(({ text }) => text),
          metadatas: passages.map(({ source, cardId }) => ({ source, cardId: cardId ?? '' })),
        }),
      });
      if (!response.ok) throw new Error(`Chroma indexing failed with ${response.status}.`);
    } catch {
      // Local persistence preserves ingestion when the optional service is offline.
    }
  }
}

export function createPassageStore(store: PraxisStore): PassageStore {
  const local = new LocalPassageStore(store);
  return process.env.CHROMA_URL ? new ChromaPassageStore(process.env.CHROMA_URL, local) : local;
}
