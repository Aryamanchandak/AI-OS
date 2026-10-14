import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { AuditReport, CardAudit, DecisionRecord, PraxisResult } from '../shared/types.js';
import type { PrincipleCard } from './schema.js';
import { personalWeight } from './cards.js';

export type Passage = { id: string; cardId?: string; source: string; text: string };
type PersistedState = { decisions: DecisionRecord[]; extraCards: PrincipleCard[]; passages: Passage[] };

const EMPTY_STATE: PersistedState = { decisions: [], extraCards: [], passages: [] };

export class PraxisStore {
  private readonly path: string;

  constructor(dataDirectory = process.env.PRAXIS_DATA_DIR || '.praxis-data') {
    const directory = resolve(process.cwd(), dataDirectory);
    mkdirSync(directory, { recursive: true });
    this.path = resolve(directory, 'state.json');
    if (!existsSync(this.path)) this.write(EMPTY_STATE);
  }

  private read(): PersistedState {
    const parsed = JSON.parse(readFileSync(this.path, 'utf8')) as Partial<PersistedState>;
    return {
      decisions: parsed.decisions ?? [],
      extraCards: parsed.extraCards ?? [],
      passages: parsed.passages ?? [],
    };
  }

  private write(state: PersistedState): void {
    const temporaryPath = `${this.path}.tmp`;
    writeFileSync(temporaryPath, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
    renameSync(temporaryPath, this.path);
  }

  allCards(baseCards: PrincipleCard[]): PrincipleCard[] {
    return [...baseCards, ...this.read().extraCards];
  }

  addIngestion(cards: PrincipleCard[], passages: Passage[]): void {
    const state = this.read();
    const known = new Set(state.extraCards.map((card) => card.id));
    state.extraCards.push(...cards.filter((card) => !known.has(card.id)));
    state.passages.push(...passages);
    this.write(state);
  }

  record(mode: 'LIVE' | 'STRIP', situation: string, result: PraxisResult): DecisionRecord {
    const state = this.read();
    const record: DecisionRecord = {
      id: randomUUID(), mode, situation, result, cardId: result.card?.id,
      createdAt: new Date().toISOString(), status: 'open',
    };
    state.decisions.unshift(record);
    this.write(state);
    return record;
  }

  decisions(): DecisionRecord[] {
    return this.read().decisions;
  }

  resolveDecision(id: string, predictionMet: boolean, outcome: string): DecisionRecord | undefined {
    const state = this.read();
    const record = state.decisions.find((item) => item.id === id);
    if (!record) return undefined;
    record.status = 'resolved';
    record.predictionMet = predictionMet;
    record.outcome = outcome;
    record.resolvedAt = new Date().toISOString();
    this.write(state);
    return record;
  }

  performance(): Record<string, { resolved: number; hits: number }> {
    const result: Record<string, { resolved: number; hits: number }> = {};
    for (const decision of this.read().decisions) {
      if (!decision.cardId || decision.status !== 'resolved') continue;
      const current = result[decision.cardId] ?? { resolved: 0, hits: 0 };
      current.resolved += 1;
      if (decision.predictionMet) current.hits += 1;
      result[decision.cardId] = current;
    }
    return result;
  }

  audit(cards: PrincipleCard[]): AuditReport {
    const decisions = this.read().decisions;
    const performance = this.performance();
    const cardRows: CardAudit[] = cards.map((card) => {
      const fired = decisions.filter((decision) => decision.cardId === card.id).length;
      const stats = performance[card.id] ?? { resolved: 0, hits: 0 };
      return {
        cardId: card.id, claim: card.claim, fired, resolved: stats.resolved, hits: stats.hits,
        hitRate: stats.resolved ? stats.hits / stats.resolved : null,
        personalWeight: personalWeight(stats),
      };
    }).sort((a, b) => a.fired - b.fired || a.personalWeight - b.personalWeight);
    const covered = cardRows.filter((row) => row.fired > 0).length;
    return {
      generatedAt: new Date().toISOString(), totalDecisions: decisions.length,
      unresolved: decisions.filter((decision) => decision.status === 'open').length,
      resolved: decisions.filter((decision) => decision.status === 'resolved').length,
      coveragePercent: cards.length ? Math.round((covered / cards.length) * 100) : 0,
      neverFired: cardRows.length - covered, cards: cardRows,
    };
  }

  passages(): Passage[] {
    return this.read().passages;
  }
}
