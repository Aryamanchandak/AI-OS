export type Mode = 'LIVE' | 'STRIP' | 'REP' | 'AUDIT';

export type PraxisResult = {
  kind: 'answer' | 'question' | 'null';
  mode: Mode;
  content: string;
  card?: {
    id: string;
    claim: string;
    replication: 'strong' | 'contested' | 'dead' | 'never-tested-outside-lab';
    source: string;
  };
  matchedCues?: string[];
};

export type PraxisRequest = {
  mode: 'LIVE' | 'STRIP';
  situation: string;
};

export type DecisionRecord = {
  id: string;
  mode: 'LIVE' | 'STRIP';
  situation: string;
  result: PraxisResult;
  cardId?: string;
  createdAt: string;
  status: 'open' | 'resolved';
  predictionMet?: boolean;
  outcome?: string;
  resolvedAt?: string;
};

export type CardAudit = {
  cardId: string;
  claim: string;
  fired: number;
  resolved: number;
  hits: number;
  hitRate: number | null;
  personalWeight: number;
};

export type AuditReport = {
  generatedAt: string;
  totalDecisions: number;
  unresolved: number;
  resolved: number;
  coveragePercent: number;
  neverFired: number;
  cards: CardAudit[];
};
