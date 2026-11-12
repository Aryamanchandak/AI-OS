import type { AuditReport, PraxisResult } from '../shared/types.js';
import { loadCards, rankCards } from './cards.js';
import { lintLive, lintStrip, NULL_ANSWER, renderLive, renderStrip } from './contracts.js';
import type { InferenceGateway } from './gateway.js';
import type { CardGraphStore } from './graph.js';
import { extractionJsonSchema, liveJsonSchema, repJsonSchema, stripJsonSchema } from './json-schemas.js';
import type { PassageStore } from './passages.js';
import { CUE_TAXONOMY, extractionPrompt, livePrompt, repPrompt, stripPrompt } from './prompts.js';
import { featureExtractionSchema, liveDraftSchema, repDraftSchema, stripDraftSchema } from './schema.js';
import type { PraxisStore } from './store.js';

export class PraxisEngine {
  constructor(
    private readonly gateway: InferenceGateway,
    private readonly store: PraxisStore,
    private readonly graph: CardGraphStore,
    private readonly passages: PassageStore,
  ) {}

  private cards() {
    return this.store.allCards(loadCards());
  }

  async run(mode: 'LIVE' | 'STRIP', situation: string): Promise<PraxisResult> {
    const extraction = await this.gateway.generateJson({
      name: 'praxis_cues', prompt: extractionPrompt(situation), schema: extractionJsonSchema,
      parser: featureExtractionSchema,
    });

    if (extraction.status === 'question') {
      const question = extraction.question.trim().replace(/\?+$/, '');
      if (!question) throw new Error('Cue extraction requested a halt without a question.');
      return { kind: 'question', mode, content: `${question}?` };
    }

    if (mode === 'STRIP') return this.runStrip(situation);

    const allowedFeatures = new Set<string>(CUE_TAXONOMY);
    const features = extraction.features.filter((feature) => allowedFeatures.has(feature));
    const ranked = rankCards(this.cards(), features, this.store.performance());
    if (ranked.length === 0) return { kind: 'null', mode, content: NULL_ANSWER, matchedCues: [] };

    const candidateIds = ranked.slice(0, 5).map(({ card }) => card.id);
    const [contradictions, passages] = await Promise.all([
      this.graph.contradictionsFor(candidateIds),
      this.passages.search(situation, candidateIds),
    ]);
    const context = { contradictions, passages: passages.map(({ source, text }) => ({ source, text })) };

    let lintFeedback = '';
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const draft = await this.gateway.generateJson({
        name: 'praxis_live', prompt: livePrompt(situation, ranked, context, lintFeedback),
        schema: liveJsonSchema, parser: liveDraftSchema,
      });
      const selected = ranked.find(({ card }) => card.id === draft.card_id);
      if (!selected) {
        lintFeedback = 'card_id was not one of the supplied candidates';
        continue;
      }
      const content = renderLive(draft);
      const lintErrors = lintLive(content);
      if (!lintErrors.length) {
        return {
          kind: 'answer', mode, content,
          card: { id: selected.card.id, claim: selected.card.claim, replication: selected.card.replication, source: selected.card.source },
          matchedCues: selected.matchedCues,
        };
      }
      lintFeedback = lintErrors.join(' ');
    }
    throw new Error('PRAXIS rejected two noncompliant LIVE drafts. Try again.');
  }

  async rep(): Promise<{ cardId: string; cardClaim: string; scenario: string; successCriterion: string }> {
    const audit = this.audit();
    const target = audit.cards
      .filter((row) => this.cards().find((card) => card.id === row.cardId)?.replication !== 'dead')
      .sort((a, b) => a.fired - b.fired || a.personalWeight - b.personalWeight)[0];
    if (!target) throw new Error('No eligible card exists for REP.');
    const card = this.cards().find((item) => item.id === target.cardId);
    if (!card) throw new Error('REP target card is missing.');
    const draft = await this.gateway.generateJson({
      name: 'praxis_rep', prompt: repPrompt(card), schema: repJsonSchema, parser: repDraftSchema,
    });
    return { cardId: card.id, cardClaim: card.claim, scenario: draft.scenario, successCriterion: draft.success_criterion };
  }

  audit(): AuditReport {
    return this.store.audit(this.cards());
  }

  private async runStrip(situation: string): Promise<PraxisResult> {
    let lintFeedback = '';
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const draft = await this.gateway.generateJson({
        name: 'praxis_strip', prompt: stripPrompt(situation, lintFeedback),
        schema: stripJsonSchema, parser: stripDraftSchema,
      });
      const content = renderStrip(draft);
      const lintErrors = lintStrip(content);
      if (!lintErrors.length) return { kind: 'answer', mode: 'STRIP', content };
      lintFeedback = lintErrors.join(' ');
    }
    throw new Error('PRAXIS rejected two noncompliant STRIP drafts. Try again.');
  }
}
