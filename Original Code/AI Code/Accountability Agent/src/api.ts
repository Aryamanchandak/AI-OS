import type { AuditReport, DecisionRecord, PraxisRequest, PraxisResult } from '../shared/types';

type ApiError = { error?: string };

export class PraxisApi {
  constructor(private readonly token: string) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(path, {
      ...init,
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${this.token}`,
        ...init?.headers,
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as ApiError;
      throw new Error(body.error || `Request failed with ${response.status}.`);
    }
    return response.json() as Promise<T>;
  }

  run(input: PraxisRequest): Promise<{ result: PraxisResult; decisionId?: string }> {
    return this.request('/api/praxis', { method: 'POST', body: JSON.stringify(input) });
  }

  rep(): Promise<{ cardId: string; cardClaim: string; scenario: string; successCriterion: string }> {
    return this.request('/api/rep', { method: 'POST' });
  }

  audit(): Promise<AuditReport> {
    return this.request('/api/audit');
  }

  decisions(): Promise<DecisionRecord[]> {
    return this.request('/api/decisions');
  }

  resolve(id: string, predictionMet: boolean, outcome: string): Promise<DecisionRecord> {
    return this.request(`/api/decisions/${id}`, {
      method: 'PATCH', body: JSON.stringify({ predictionMet, outcome }),
    });
  }

  ingest(input: { title: string; author: string; sourceText: string }): Promise<{ cards: Array<{ id: string; claim: string }>; passageCount: number }> {
    return this.request('/api/ingest', { method: 'POST', body: JSON.stringify(input) });
  }

  graph(): Promise<{ cards: unknown[]; cues: string[]; cardCueEdges: unknown[]; contradictions: unknown[] }> {
    return this.request('/api/graph');
  }
}
