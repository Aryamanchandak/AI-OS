import { describe, expect, it } from 'vitest';
import { lintLive, lintStrip, NULL_ANSWER, renderLive, renderStrip, wordCount } from './contracts.js';

describe('ruthless output contracts', () => {
  it('renders a compliant LIVE answer with prediction and forced discard', () => {
    const output = renderLive({
      card_id: 'recip-003', move: 'Open at 100 and retreat once to 70.',
      rationale: 'The other side can make a reciprocal concession.',
      prediction: 'They counter within two days at 60 or above.', tension: '', grounding: '',
      ignoring: ['tone polishing', 'extra options'],
    });
    expect(wordCount(output)).toBeLessThanOrEqual(120);
    expect(lintLive(output)).toEqual([]);
    expect(output.endsWith('Ignoring: tone polishing, extra options')).toBe(true);
  });

  it('rejects hedging, lists, missing predictions, and excess length', () => {
    const bad = `- It depends. ${'word '.repeat(125)}\nIgnoring: one, two`;
    expect(lintLive(bad).length).toBeGreaterThanOrEqual(3);
  });

  it('renders STRIP around one variable and preserves NULL verbatim', () => {
    expect(lintStrip(renderStrip({ variable: 'reversibility', directive: 'Run the cheap test today.', ignoring: ['title', 'presentation'] }))).toEqual([]);
    expect(NULL_ANSWER).toBe('No card in your corpus applies. This is execution, not strategy. Go do it.');
  });
});
