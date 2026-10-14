import type { RankedCard } from './cards.js';

export const CUE_TAXONOMY = [
  'information_asymmetry', 'repeated_game', 'one_shot', 'status_differential',
  'status_higher', 'status_peer', 'status_lower', 'audience_present', 'sunk_cost_live',
  'ambiguity', 'risk', 'you_move_first', 'they_move_first', 'reversible', 'irreversible',
  'trust_low', 'trust_not_low', 'trust_high', 'time_pressure', 'disagreement', 'negotiation',
  'social_uncertainty', 'emotional_heat', 'multiple_options', 'objective_standard_available',
  'objective_standard_missing', 'relationship_matters', 'commitment_missing', 'outcome_known',
  'decision_review', 'group_decision', 'power_imbalance', 'multiple_steps', 'planning', 'scarcity_real',
] as const;

export function extractionPrompt(situation: string): string {
  return `You are the cue extractor for PRAXIS. Read the situation and return only controlled situational features.

Allowed features: ${CUE_TAXONOMY.join(', ')}.

If one missing fact would change the recommended action, set status to "question", ask exactly one short question, and return no features. Do not ask for merely useful context. Otherwise set status to "ready", question to an empty string, and include only features directly supported by the text. Never invent facts.

Situation:
${situation}`;
}

export function livePrompt(
  situation: string,
  ranked: RankedCard[],
  context: { contradictions: unknown[]; passages: Array<{ source: string; text: string }> },
  lintFeedback = '',
): string {
  const candidates = ranked.slice(0, 5).map(({ card, matchedCues, score }) => ({
    ...card,
    matched_cues: matchedCues,
    cue_score: Number(score.toFixed(2)),
    personal_weight: Number(ranked.find((item) => item.card.id === card.id)?.personalWeight.toFixed(2)),
  }));

  return `You are PRAXIS in LIVE mode. Choose exactly one candidate card and prescribe one concrete move. No alternatives. The prediction must name an observable result, threshold, and time window. The rationale must be one short sentence. Supply exactly two short ignored factors. Never use these phrases: "it depends", "consider", "you might", "both approaches have merit". Keep the rendered answer under 120 words. If a contradiction involves the selected card, state the competing principle and why the situation favors this one in the tension field; otherwise use an empty string. If a supplied passage directly grounds a boundary condition, copy no more than 20 words verbatim into grounding; otherwise use an empty string. Never quote candidate-card prose as if it were verbatim source text.

${lintFeedback ? `The prior draft failed lint: ${lintFeedback}. Correct every failure.\n\n` : ''}Situation:
${situation}

Ranked candidates:
${JSON.stringify(candidates, null, 2)}

Contradictions among candidates:
${JSON.stringify(context.contradictions, null, 2)}

User-supplied grounding passages:
${JSON.stringify(context.passages, null, 2)}`;
}

export function repPrompt(card: { id: string; claim: string; cues: string[]; move: string; failure_mode: string }): string {
  return `Create one realistic, compact practice situation that specifically tests whether the user can apply this principle card. Do not name the card or reveal the move. Include enough information to act and one tempting distraction. The success criterion must state the observable move the user should make.\n\nCard:\n${JSON.stringify(card, null, 2)}`;
}

export function ingestionPrompt(title: string, author: string, sourceText: string): string {
  return `Destructure the supplied text into 1 to 5 atomic PRAXIS principle cards. A card must prescribe a move, not summarize prose. Use only these cues: ${CUE_TAXONOMY.join(', ')}. Source must name ${author}, ${title}, plus a heading or location actually visible in the supplied text. Be conservative about replication: use strong only for claims the supplied text itself ties to robust replicated evidence; use contested for disputed evidence; dead for failed effects; otherwise use never-tested-outside-lab. Never invent quotations, page numbers, evidence, or claims absent from the text. IDs must be lowercase kebab-case.\n\nSource text:\n${sourceText}`;
}

export function stripPrompt(situation: string, lintFeedback = ''): string {
  return `You are PRAXIS in STRIP mode. Identify exactly one decision variable that carries the choice. State one direct action controlled by it. Explain no theory. Supply exactly two short ignored factors. Never use these phrases: "it depends", "consider", "you might", "both approaches have merit".

${lintFeedback ? `The prior draft failed lint: ${lintFeedback}. Correct every failure.\n\n` : ''}Situation:
${situation}`;
}
