export const extractionJsonSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['status', 'question', 'features'],
  properties: {
    status: { type: 'string', enum: ['ready', 'question'] },
    question: { type: 'string' },
    features: { type: 'array', items: { type: 'string' } },
  },
};

export const liveJsonSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['card_id', 'move', 'rationale', 'prediction', 'tension', 'grounding', 'ignoring'],
  properties: {
    card_id: { type: 'string' },
    move: { type: 'string' },
    rationale: { type: 'string' },
    prediction: { type: 'string' },
    tension: { type: 'string' },
    grounding: { type: 'string' },
    ignoring: { type: 'array', minItems: 2, maxItems: 2, items: { type: 'string' } },
  },
};

export const stripJsonSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['variable', 'directive', 'ignoring'],
  properties: {
    variable: { type: 'string' },
    directive: { type: 'string' },
    ignoring: { type: 'array', minItems: 2, maxItems: 2, items: { type: 'string' } },
  },
};

export const repJsonSchema = {
  type: 'object', additionalProperties: false, required: ['scenario', 'success_criterion'],
  properties: { scenario: { type: 'string' }, success_criterion: { type: 'string' } },
};

export const ingestionJsonSchema = {
  type: 'object', additionalProperties: false, required: ['cards'],
  properties: {
    cards: {
      type: 'array', minItems: 1, maxItems: 5,
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'claim', 'mechanism', 'cues', 'move', 'preconditions', 'failure_mode', 'replication', 'source'],
        properties: {
          id: { type: 'string' }, claim: { type: 'string' }, mechanism: { type: 'string' },
          cues: { type: 'array', minItems: 1, items: { type: 'string' } }, move: { type: 'string' },
          preconditions: { type: 'string' }, failure_mode: { type: 'string' },
          replication: { type: 'string', enum: ['strong', 'contested', 'dead', 'never-tested-outside-lab'] },
          source: { type: 'string' },
        },
      },
    },
  },
};
