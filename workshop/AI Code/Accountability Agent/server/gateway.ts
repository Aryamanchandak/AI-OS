import OpenAI from 'openai';
import type { ZodType } from 'zod';

export interface InferenceGateway {
  generateJson<T>(options: {
    name: string;
    prompt: string;
    schema: Record<string, unknown>;
    parser: ZodType<T>;
  }): Promise<T>;
}

export class OpenAIResponsesGateway implements InferenceGateway {
  private readonly client: OpenAI;

  constructor(
    apiKey: string,
    private readonly model = process.env.OPENAI_MODEL || 'gpt-5.6-terra',
  ) {
    this.client = new OpenAI({ apiKey, timeout: 30_000, maxRetries: 2 });
  }

  async generateJson<T>({ name, prompt, schema, parser }: {
    name: string;
    prompt: string;
    schema: Record<string, unknown>;
    parser: ZodType<T>;
  }): Promise<T> {
    const response = await this.client.responses.create({
      model: this.model,
      reasoning: { effort: 'low' },
      input: prompt,
      text: { format: { type: 'json_schema', name, strict: true, schema } },
    });
    if (!response.output_text) throw new Error('The inference gateway returned no text output.');
    return parser.parse(JSON.parse(response.output_text) as unknown);
  }
}
