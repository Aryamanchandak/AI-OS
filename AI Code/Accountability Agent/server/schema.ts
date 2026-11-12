import { z } from 'zod';

export const replicationSchema = z.enum([
  'strong',
  'contested',
  'dead',
  'never-tested-outside-lab',
]);

export const cardSchema = z.object({
  id: z.string().min(1),
  claim: z.string().min(1),
  mechanism: z.string().min(1),
  cues: z.array(z.string().min(1)).min(1),
  move: z.string().min(1),
  preconditions: z.string().min(1),
  failure_mode: z.string().min(1),
  replication: replicationSchema,
  source: z.string().min(1),
});

export const cardsSchema = z.array(cardSchema).length(15);
export type PrincipleCard = z.infer<typeof cardSchema>;

export const requestSchema = z.object({
  mode: z.enum(['LIVE', 'STRIP']),
  situation: z.string().trim().min(12, 'Give PRAXIS at least 12 characters of context.').max(4000),
});

export const ingestionRequestSchema = z.object({
  title: z.string().trim().min(1).max(200),
  author: z.string().trim().min(1).max(200),
  sourceText: z.string().trim().min(500).max(200000),
});

export const resolutionSchema = z.object({
  predictionMet: z.boolean(),
  outcome: z.string().trim().min(1).max(2000),
});

export const ingestedCardsSchema = z.object({
  cards: z.array(cardSchema.omit({ id: true }).extend({ id: z.string() })).min(1).max(5),
});

export const repDraftSchema = z.object({
  scenario: z.string().min(1),
  success_criterion: z.string().min(1),
});

export const featureExtractionSchema = z.object({
  status: z.enum(['ready', 'question']),
  question: z.string(),
  features: z.array(z.string()),
});

export const liveDraftSchema = z.object({
  card_id: z.string(),
  move: z.string().min(1),
  rationale: z.string().min(1),
  prediction: z.string().min(1),
  tension: z.string(),
  grounding: z.string(),
  ignoring: z.array(z.string().min(1)).length(2),
});

export const stripDraftSchema = z.object({
  variable: z.string().min(1),
  directive: z.string().min(1),
  ignoring: z.array(z.string().min(1)).length(2),
});

export type FeatureExtraction = z.infer<typeof featureExtractionSchema>;
export type LiveDraft = z.infer<typeof liveDraftSchema>;
export type StripDraft = z.infer<typeof stripDraftSchema>;
