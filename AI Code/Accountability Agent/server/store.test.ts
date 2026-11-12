import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { loadCards } from './cards.js';
import { PraxisStore } from './store.js';

const directories: string[] = [];

afterEach(() => {
  for (const directory of directories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

describe('decision tracker and audit', () => {
  it('writes a prediction, resolves it, and updates card weight and coverage', () => {
    const directory = mkdtempSync(join(tmpdir(), 'praxis-test-'));
    directories.push(directory);
    const store = new PraxisStore(directory);
    const card = loadCards()[0];
    const decision = store.record('LIVE', 'A concrete negotiation situation.', {
      kind: 'answer', mode: 'LIVE', content: 'Prediction: reply tomorrow.\n\nIgnoring: tone, title',
      card: { id: card.id, claim: card.claim, replication: card.replication, source: card.source },
    });
    expect(store.resolveDecision(decision.id, false, 'They did not reply.')).toMatchObject({ status: 'resolved', predictionMet: false });
    const audit = store.audit(loadCards());
    expect(audit.totalDecisions).toBe(1);
    expect(audit.coveragePercent).toBeGreaterThan(0);
    expect(audit.cards.find((row) => row.cardId === card.id)).toMatchObject({ fired: 1, resolved: 1, hits: 0 });
  });
});
