import { callAI, callAIJSON } from '@/lib/ai';
import {
  PROMPT_SECTION_DETECTOR,
  PROMPT_CONTEXT_EXTRACTOR,
  PROMPT_ITERATION,
  PROMPT_CONFLICT_DETECTOR,
  PROMPT_LLM_JUDGE,
} from '@/lib/prompts';
import type {
  Mode,
  Section,
  ProjectContext,
  TestCase,
  TestResult,
  AssertionResult,
  Conflict,
  IterationResult,
  Document,
  ChatMessage,
} from '@/lib/types';

export async function detectSections(rawInput: string, mode: Mode): Promise<Section[]> {
  const result = await callAIJSON<{ sections: Omit<Section, 'id' | 'history'>[] }>({
    system: PROMPT_SECTION_DETECTOR(mode),
    userMessage: rawInput,
    maxTokens: 4000,
  });
  return result.sections.map((s, i) => ({
    id: `s${i + 1}`,
    title: s.title,
    kind: s.kind,
    content: s.content,
    rationale: s.rationale,
    history: [],
  }));
}

export async function extractContext(rawText: string): Promise<ProjectContext> {
  const extracted = await callAIJSON<ProjectContext['extracted']>({
    system: PROMPT_CONTEXT_EXTRACTOR,
    userMessage: rawText,
    maxTokens: 1500,
  });
  return { raw: rawText, extracted };
}

export async function iterateSection({
  mode,
  section,
  fullDocument,
  projectContext,
  chatHistory,
  userMessage,
  guidePrompt,
}: {
  mode: Mode;
  section: Section;
  fullDocument: string;
  projectContext: ProjectContext | null;
  chatHistory: ChatMessage[];
  userMessage: string;
  guidePrompt?: string;
}): Promise<IterationResult> {
  const result = await callAIJSON<{
    rewritten_content: string;
    reasoning: string;
    clarifying_question: string | null;
    suggested_context_update: string | null;
  }>({
    system: PROMPT_ITERATION({
      mode,
      projectContext: projectContext?.extracted ?? null,
      fullDocument,
      currentSection: section,
      chatHistory,
      userMessage,
      guidePrompt,
    }),
    userMessage,
    maxTokens: 3000,
  });
  return {
    rewrittenContent: result.rewritten_content,
    reasoning: result.reasoning,
    clarifyingQuestion: result.clarifying_question || null,
    suggestedContextUpdate: result.suggested_context_update || null,
  };
}

export async function detectConflicts({
  sections,
  editedSectionId,
  projectContext,
}: {
  sections: Section[];
  editedSectionId: string;
  projectContext: ProjectContext | null;
}): Promise<Conflict[]> {
  const result = await callAIJSON<{ conflicts: Conflict[] }>({
    system: PROMPT_CONFLICT_DETECTOR({
      sections,
      editedSectionId,
      projectContext: projectContext?.extracted ?? null,
    }),
    userMessage: 'Check for conflicts now.',
    maxTokens: 1500,
  });
  return result.conflicts || [];
}

export function renderTemplate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => {
    if (key in vars) return vars[key];
    return `{{${key}}}`;
  });
}

export async function evaluateAssertion({
  assertion,
  output,
  projectContext,
}: {
  assertion: import('@/lib/types').Assertion;
  output: string;
  projectContext: ProjectContext | null;
}): Promise<{ passed: boolean; reasoning: string }> {
  switch (assertion.type) {
    case 'substring': {
      const has = output.includes(assertion.spec.text ?? '');
      const passed = assertion.spec.mode === 'must_include' ? has : !has;
      return {
        passed,
        reasoning: passed
          ? `Output ${assertion.spec.mode === 'must_include' ? 'contains' : 'does not contain'} "${assertion.spec.text}"`
          : `Output ${assertion.spec.mode === 'must_include' ? 'is missing' : 'unexpectedly contains'} "${assertion.spec.text}"`,
      };
    }
    case 'structural': {
      try {
        const cleaned = output
          .replace(/^```(?:json)?\s*/i, '')
          .replace(/\s*```$/, '')
          .trim();
        const parsed = JSON.parse(cleaned);
        if (assertion.spec.schema === 'json_with_keys') {
          const missing = (assertion.spec.keys || []).filter(k => !(k in parsed));
          if (missing.length > 0) {
            return { passed: false, reasoning: `JSON missing keys: ${missing.join(', ')}` };
          }
        }
        return { passed: true, reasoning: 'Output is valid JSON with required keys' };
      } catch {
        return { passed: false, reasoning: 'Output is not valid JSON' };
      }
    }
    case 'semantic': {
      const judgment = await callAIJSON<{ passed: boolean; reasoning: string }>({
        system: PROMPT_LLM_JUDGE({
          criterion: assertion.spec.criterion ?? '',
          output,
          projectContext: projectContext?.extracted ?? null,
        }),
        userMessage: 'Judge now.',
        maxTokens: 500,
      });
      return { passed: judgment.passed, reasoning: judgment.reasoning };
    }
    case 'reference': {
      const tokenize = (s: string): string[] => s.toLowerCase().match(/\w+/g) ?? [];
      const aArr = tokenize(output);
      const bArr = tokenize(assertion.spec.reference ?? '');
      const b = new Set<string>(bArr);
      const intersection = aArr.filter(x => b.has(x)).length;
      const union = new Set<string>([...aArr, ...bArr]).size;
      const sim = union === 0 ? 0 : intersection / union;
      const threshold = assertion.spec.similarity_threshold ?? 0.5;
      return {
        passed: sim >= threshold,
        reasoning: `Jaccard similarity ${sim.toFixed(2)} vs threshold ${threshold}`,
      };
    }
    default:
      return { passed: false, reasoning: `Unknown assertion type: ${(assertion as { type: string }).type}` };
  }
}

export async function runTest({
  promptDocument,
  testCase,
  projectContext,
}: {
  promptDocument: Document;
  testCase: TestCase;
  projectContext: ProjectContext | null;
}): Promise<TestResult> {
  const fullPrompt = promptDocument.sections.map(s => s.content).join('\n\n');
  const renderedPrompt = renderTemplate(fullPrompt, testCase.inputVars);

  const startTime = Date.now();
  let output: string;
  try {
    output = await callAI({
      system: renderedPrompt,
      userMessage: testCase.context || '(no user message provided)',
      maxTokens: 2000,
    });
  } catch (e) {
    return {
      testCaseId: testCase.id,
      output: null,
      error: (e as Error).message,
      assertions: [],
      latencyMs: Date.now() - startTime,
      passed: false,
    };
  }
  const latencyMs = Date.now() - startTime;

  const assertionResults: AssertionResult[] = [];
  for (const assertion of testCase.assertions) {
    const r = await evaluateAssertion({ assertion, output, projectContext });
    assertionResults.push({ ...r, assertion });
  }

  return {
    testCaseId: testCase.id,
    output,
    error: null,
    assertions: assertionResults,
    latencyMs,
    passed: assertionResults.every(r => r.passed),
  };
}
