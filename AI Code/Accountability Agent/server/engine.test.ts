import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import type { ZodType } from 'zod';
import { PraxisEngine } from './engine.js';
import type { InferenceGateway } from './gateway.js';
import { LocalCardGraphStore } from './graph.js';
import { LocalPassageStore } from './passages.js';
import { PraxisStore } from './store.js';

class QueueGateway implements InferenceGateway {
  constructor(private readonly queue: unknown[]) {}

  async generateJson<T>({ parser }: { name: string; prompt: string; schema: Record<string, unknown>; parser: ZodType<T> }): Promise<T> {
    return parser.parse(this.queue.shift());
  }
}

const directories: string[] = [];
afterEach(() => {
  for (const directory of directories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

function fixture(queue: unknown[]) {
  const directory = mkdtempSync(join(tmpdir(), 'praxis-engine-'));
  directories.push(directory);
  const store = new PraxisStore(directory);
  return new PraxisEngine(new QueueGateway(queue), store, new LocalCardGraphStore(), new LocalPassageStore(store));
}

describe('PRAXIS engine modes', () => {
  it('halts with exactly one question when the load-bearing variable is absent', async () => {
    const engine = fixture([{ status: 'question', question: 'Is the decision reversible?', features: [] }]);
    await expect(engine.run('LIVE', 'We need to choose a path with incomplete context.')).resolves.toEqual({
      kind: 'question', mode: 'LIVE', content: 'Is the decision reversible?',
    });
  });

  it('returns NULL rather than forcing a zero-cue card match', async () => {
    const engine = fixture([{ status: 'ready', question: '', features: [] }]);
    await expect(engine.run('LIVE', 'The task is already decided and only needs execution.')).resolves.toMatchObject({
      kind: 'null', content: 'No card in your corpus applies. This is execution, not strategy. Go do it.',
    });
  });

  it('renders a constrained STRIP answer', async () => {
    const engine = fixture([
      { status: 'ready', question: '', features: ['reversible'] },
      { variable: 'cost of reversal', directive: 'Run the smallest reversible test today.', ignoring: ['presentation polish', 'title hierarchy'] },
    ]);
    const result = await engine.run('STRIP', 'The team is debating two reversible prototypes instead of testing either.');
    expect(result.kind).toBe('answer');
    expect(result.content).toContain('Load-bearing variable: cost of reversal');
    expect(result.content).toMatch(/Ignoring: presentation polish, title hierarchy$/);
  });
});
