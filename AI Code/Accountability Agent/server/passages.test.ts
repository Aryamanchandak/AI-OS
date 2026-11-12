import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { LocalPassageStore } from './passages.js';
import { PraxisStore } from './store.js';

const directories: string[] = [];
afterEach(() => {
  for (const directory of directories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

describe('local passage grounding', () => {
  it('retrieves user-supplied boundary-condition text by lexical overlap', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'praxis-passages-'));
    directories.push(directory);
    const store = new PraxisStore(directory);
    store.addIngestion([], [
      { id: 'p1', source: 'Test source', text: 'A concession works only when the opening request remains plausible.' },
      { id: 'p2', source: 'Other source', text: 'Unrelated material about scheduling.' },
    ]);
    const results = await new LocalPassageStore(store).search('Is this concession request plausible?', []);
    expect(results[0]).toMatchObject({ id: 'p1', source: 'Test source' });
  });
});
