export type Mode = 'prompt' | 'plan';

export interface Iteration {
  timestamp: number;
  userMessage: string;
  oldContent: string;
  newContent: string;
  reasoning: string;
}

export interface Section {
  id: string;
  title: string;
  kind: string;
  content: string;
  rationale: string;
  history: Iteration[];
}

export interface AssertionSpec {
  mode?: 'must_include' | 'must_not_include';
  text?: string;
  schema?: 'json' | 'json_with_keys';
  keys?: string[];
  criterion?: string;
  reference?: string;
  similarity_threshold?: number;
}

export interface Assertion {
  type: 'substring' | 'structural' | 'semantic' | 'reference';
  spec: AssertionSpec;
}

export interface TestCase {
  id: string;
  name: string;
  inputVars: Record<string, string>;
  context: string;
  assertions: Assertion[];
  tags: string[];
}

export interface AssertionResult {
  passed: boolean;
  reasoning: string;
  assertion: Assertion;
}

export interface TestResult {
  testCaseId: string;
  output: string | null;
  error: string | null;
  assertions: AssertionResult[];
  latencyMs: number;
  passed: boolean;
}

export interface Conflict {
  section_id: string;
  type: 'contradiction' | 'redundancy' | 'orphan';
  description: string;
}

export interface ExtractedContext {
  goal: string;
  tech_stack: string[];
  constraints: string[];
  key_decisions: string[];
  architecture_notes: string;
  open_questions: string[];
}

export interface ProjectContext {
  raw: string;
  extracted: ExtractedContext;
}

export interface Document {
  id: string;
  mode: Mode;
  rawInput: string;
  sections: Section[];
  testCases: TestCase[];
}

export interface Version {
  timestamp: number;
  document: Document;
  testResults: Record<string, TestResult> | null;
  conflicts: Conflict[] | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  suggestedContextUpdate?: string | null;
  clarifyingQuestion?: string | null;
  isRewrite?: boolean;
}

export interface IterationResult {
  rewrittenContent: string;
  reasoning: string;
  clarifyingQuestion: string | null;
  suggestedContextUpdate: string | null;
}
