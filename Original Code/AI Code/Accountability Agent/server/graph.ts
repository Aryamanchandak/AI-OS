import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { PrincipleCard } from './schema.js';

export type Contradiction = { from: string; to: string; reason: string };
export type GraphSnapshot = {
  cards: Array<{ id: string; claim: string }>;
  cues: string[];
  cardCueEdges: Array<{ cardId: string; cue: string }>;
  contradictions: Contradiction[];
};

export interface CardGraphStore {
  contradictionsFor(cardIds: string[]): Promise<Contradiction[]>;
  snapshot(cards: PrincipleCard[]): Promise<GraphSnapshot>;
}

export class LocalCardGraphStore implements CardGraphStore {
  private contradictions(): Contradiction[] {
    return JSON.parse(readFileSync(resolve(process.cwd(), 'data/contradictions.json'), 'utf8')) as Contradiction[];
  }

  async contradictionsFor(cardIds: string[]): Promise<Contradiction[]> {
    const ids = new Set(cardIds);
    return this.contradictions().filter((edge) => ids.has(edge.from) && ids.has(edge.to));
  }

  async snapshot(cards: PrincipleCard[]): Promise<GraphSnapshot> {
    return {
      cards: cards.map(({ id, claim }) => ({ id, claim })),
      cues: [...new Set(cards.flatMap((card) => card.cues))].sort(),
      cardCueEdges: cards.flatMap((card) => card.cues.map((cue) => ({ cardId: card.id, cue }))),
      contradictions: this.contradictions(),
    };
  }
}

export class Neo4jCardGraphStore implements CardGraphStore {
  constructor(
    private readonly uri: string,
    private readonly username: string,
    private readonly password: string,
    private readonly fallback = new LocalCardGraphStore(),
  ) {}

  private async query(statement: string, parameters: Record<string, unknown>): Promise<unknown[][]> {
    const endpoint = `${this.uri.replace(/\/$/, '')}/db/neo4j/tx/commit`;
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Basic ${Buffer.from(`${this.username}:${this.password}`).toString('base64')}`,
      },
      body: JSON.stringify({ statements: [{ statement, parameters }] }),
    });
    if (!response.ok) throw new Error(`Neo4j adapter failed with ${response.status}.`);
    const body = await response.json() as { results?: Array<{ data?: Array<{ row: unknown[] }> }>; errors?: unknown[] };
    if (body.errors?.length) throw new Error('Neo4j returned a query error.');
    return body.results?.[0]?.data?.map(({ row }) => row) ?? [];
  }

  async contradictionsFor(cardIds: string[]): Promise<Contradiction[]> {
    try {
      const rows = await this.query(
        'MATCH (a:Card)-[r:CONTRADICTS]-(b:Card) WHERE a.id IN $ids AND b.id IN $ids RETURN a.id, b.id, r.reason',
        { ids: cardIds },
      );
      if (!rows.length) return this.fallback.contradictionsFor(cardIds);
      return rows.map((row) => ({ from: String(row[0]), to: String(row[1]), reason: String(row[2]) }));
    } catch {
      return this.fallback.contradictionsFor(cardIds);
    }
  }

  async snapshot(cards: PrincipleCard[]): Promise<GraphSnapshot> {
    const snapshot = await this.fallback.snapshot(cards);
    try {
      await this.query(
        'UNWIND $cards AS card MERGE (c:Card {id: card.id}) SET c.claim = card.claim',
        { cards: snapshot.cards },
      );
      await this.query(
        'UNWIND $edges AS edge MATCH (c:Card {id: edge.cardId}) MERGE (q:Cue {name: edge.cue}) MERGE (c)-[:HAS_CUE]->(q)',
        { edges: snapshot.cardCueEdges },
      );
      await this.query(
        'UNWIND $edges AS edge MATCH (a:Card {id: edge.from}), (b:Card {id: edge.to}) MERGE (a)-[r:CONTRADICTS]->(b) SET r.reason = edge.reason',
        { edges: snapshot.contradictions },
      );
    } catch {
      // The local snapshot remains authoritative when the optional service is offline.
    }
    return snapshot;
  }
}

export function createGraphStore(): CardGraphStore {
  if (process.env.NEO4J_URI && process.env.NEO4J_USERNAME && process.env.NEO4J_PASSWORD) {
    return new Neo4jCardGraphStore(process.env.NEO4J_URI, process.env.NEO4J_USERNAME, process.env.NEO4J_PASSWORD);
  }
  return new LocalCardGraphStore();
}
