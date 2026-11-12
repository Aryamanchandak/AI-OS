import type { Document, Version, TestResult, Conflict } from '@/lib/types';

export function snapshotDocument(
  document: Document,
  testResults: Record<string, TestResult> | null,
  conflicts: Conflict[] | null
): Version {
  return {
    timestamp: Date.now(),
    document: JSON.parse(JSON.stringify(document)),
    testResults: testResults ? JSON.parse(JSON.stringify(testResults)) : null,
    conflicts: conflicts ? JSON.parse(JSON.stringify(conflicts)) : null,
  };
}

export function classifyTestChanges(
  prev: Record<string, TestResult> | null,
  current: Record<string, TestResult>
): Record<string, 'regression' | 'new_pass' | 'unchanged'> {
  const out: Record<string, 'regression' | 'new_pass' | 'unchanged'> = {};
  for (const [id, result] of Object.entries(current)) {
    const prevResult = prev?.[id];
    if (!prevResult) {
      out[id] = 'unchanged';
      continue;
    }
    if (prevResult.passed && !result.passed) out[id] = 'regression';
    else if (!prevResult.passed && result.passed) out[id] = 'new_pass';
    else out[id] = 'unchanged';
  }
  return out;
}
