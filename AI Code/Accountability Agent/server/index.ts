import 'dotenv/config';
import { existsSync } from 'node:fs';
import { timingSafeEqual } from 'node:crypto';
import { resolve } from 'node:path';
import express from 'express';
import { ZodError } from 'zod';
import { PraxisEngine } from './engine.js';
import { OpenAIResponsesGateway } from './gateway.js';
import { createGraphStore } from './graph.js';
import { IngestionService } from './ingestion.js';
import { createPassageStore } from './passages.js';
import { ingestionRequestSchema, requestSchema, resolutionSchema } from './schema.js';
import { loadCards } from './cards.js';
import { PraxisStore } from './store.js';

const app = express();
const port = Number(process.env.PORT || 8787);
const store = new PraxisStore();
const graph = createGraphStore();
const passages = createPassageStore(store);

function gateway(): OpenAIResponsesGateway {
  if (!process.env.OPENAI_API_KEY) throw new Error('OPENAI_API_KEY is not configured on the server.');
  return new OpenAIResponsesGateway(process.env.OPENAI_API_KEY);
}

function engine(): PraxisEngine {
  return new PraxisEngine(gateway(), store, graph, passages);
}

function equalTokens(actual: string, expected: string): boolean {
  const left = Buffer.from(actual);
  const right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}

app.disable('x-powered-by');
app.use(express.json({ limit: '256kb' }));

app.get('/api/health', (_request, response) => {
  response.json({ ok: true, product: 'PRAXIS', authRequired: true });
});

app.use('/api', (request, response, next) => {
  const expected = process.env.PRAXIS_ACCESS_TOKEN;
  if (!expected) {
    response.status(503).json({ error: 'PRAXIS_ACCESS_TOKEN is not configured on the server.' });
    return;
  }
  const actual = request.header('authorization')?.replace(/^Bearer\s+/i, '') ?? '';
  if (!equalTokens(actual, expected)) {
    response.status(401).json({ error: 'Access token rejected.' });
    return;
  }
  next();
});

app.post('/api/praxis', async (request, response, next) => {
  try {
    const input = requestSchema.parse(request.body);
    const result = await engine().run(input.mode, input.situation);
    const decision = result.kind === 'question' ? undefined : store.record(input.mode, input.situation, result);
    response.json({ result, decisionId: decision?.id });
  } catch (error) { next(error); }
});

app.post('/api/rep', async (_request, response, next) => {
  try { response.json(await engine().rep()); } catch (error) { next(error); }
});

app.get('/api/audit', (_request, response) => {
  response.json(store.audit(store.allCards(loadCards())));
});

app.get('/api/decisions', (_request, response) => {
  response.json(store.decisions());
});

app.patch('/api/decisions/:id', (request, response, next) => {
  try {
    const resolution = resolutionSchema.parse(request.body);
    const decision = store.resolveDecision(request.params.id, resolution.predictionMet, resolution.outcome);
    if (!decision) { response.status(404).json({ error: 'Decision not found.' }); return; }
    response.json(decision);
  } catch (error) { next(error); }
});

app.post('/api/ingest', async (request, response, next) => {
  try {
    const input = ingestionRequestSchema.parse(request.body);
    response.json(await new IngestionService(gateway(), store, passages).ingest(input.title, input.author, input.sourceText));
  } catch (error) { next(error); }
});

app.get('/api/graph', async (_request, response, next) => {
  try { response.json(await graph.snapshot(store.allCards(loadCards()))); } catch (error) { next(error); }
});

app.use((error: unknown, _request: express.Request, response: express.Response, _next: express.NextFunction) => {
  if (error instanceof ZodError) {
    response.status(400).json({ error: error.issues[0]?.message || 'Invalid request.' });
    return;
  }
  const message = error instanceof Error ? error.message : 'PRAXIS failed unexpectedly.';
  console.error(error);
  response.status(502).json({ error: message });
});

const staticPath = resolve(process.cwd(), 'dist');
app.use(express.static(staticPath));
app.use((request, response, next) => {
  const indexPath = resolve(staticPath, 'index.html');
  if (request.method === 'GET' && existsSync(indexPath)) response.sendFile(indexPath);
  else next();
});

app.listen(port, '0.0.0.0', () => {
  console.log(`PRAXIS listening on http://0.0.0.0:${port}`);
});
