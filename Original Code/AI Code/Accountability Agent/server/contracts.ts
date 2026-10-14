import type { LiveDraft, StripDraft } from './schema.js';

const BANNED = [
  /\bit depends\b/i,
  /\bconsider\b/i,
  /\byou might\b/i,
  /\bboth approaches have merit\b/i,
];

export const NULL_ANSWER = 'No card in your corpus applies. This is execution, not strategy. Go do it.';

export function wordCount(value: string): number {
  return value.trim().match(/\S+/g)?.length ?? 0;
}

export function renderLive(draft: LiveDraft): string {
  const tension = draft.tension ? ` Tension: ${draft.tension}` : '';
  const grounding = draft.grounding ? ` Grounding: “${draft.grounding}”` : '';
  return `Apply ${draft.card_id}. ${draft.move} ${draft.rationale}${tension}${grounding} Prediction: ${draft.prediction}\n\nIgnoring: ${draft.ignoring.join(', ')}`;
}

export function renderStrip(draft: StripDraft): string {
  return `Load-bearing variable: ${draft.variable}\n\n${draft.directive}\n\nIgnoring: ${draft.ignoring.join(', ')}`;
}

export function lintLive(output: string): string[] {
  const errors: string[] = [];
  if (wordCount(output) > 120) errors.push('LIVE output exceeds 120 words.');
  if (/^\s*(?:[-*•]|\d+[.)])\s/m.test(output)) errors.push('LIVE output contains a list.');
  if (!/Ignoring: [^,\n]+, [^\n]+\s*$/.test(output)) errors.push('LIVE output must end with exactly two ignored items.');
  if (!/\bPrediction:/i.test(output)) errors.push('LIVE output lacks a falsifiable prediction.');
  for (const phrase of BANNED) {
    if (phrase.test(output)) errors.push(`LIVE output contains banned hedge: ${phrase.source}`);
  }
  return errors;
}

export function lintStrip(output: string): string[] {
  const errors: string[] = [];
  if (!/^Load-bearing variable:/i.test(output)) errors.push('STRIP output lacks one load-bearing variable.');
  if (!/Ignoring: [^,\n]+, [^\n]+\s*$/.test(output)) errors.push('STRIP output must end with exactly two ignored items.');
  for (const phrase of BANNED) {
    if (phrase.test(output)) errors.push(`STRIP output contains banned hedge: ${phrase.source}`);
  }
  return errors;
}
