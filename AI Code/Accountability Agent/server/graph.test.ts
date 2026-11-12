import { describe, expect, it } from 'vitest';
import { loadCards } from './cards.js';
import { LocalCardGraphStore } from './graph.js';

describe('card and cue graph', () => {
  it('materializes card nodes, cue nodes, HAS_CUE edges, and contradictions', async () => {
    const graph = await new LocalCardGraphStore().snapshot(loadCards());
    expect(graph.cards).toHaveLength(15);
    expect(graph.cues.length).toBeGreaterThanOrEqual(20);
    expect(graph.cardCueEdges.length).toBeGreaterThan(15);
    expect(graph.contradictions.length).toBeGreaterThan(0);
  });
});
