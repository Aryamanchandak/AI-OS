// Available OpenAI models — update ACTIVE_MODEL to switch.
export const MODELS = {
  'gpt-4o':       'gpt-4o',
  'gpt-4o-mini':  'gpt-4o-mini',
  'gpt-4-turbo':  'gpt-4-turbo',
  'o1-mini':      'o1-mini',
} as const;

export const ACTIVE_MODEL: string = MODELS['gpt-4o-mini'];
