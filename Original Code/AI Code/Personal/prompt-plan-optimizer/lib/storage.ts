import type { Document, ProjectContext, Version } from '@/lib/types';

const KEYS = {
  document: 'optimizer:doc',
  context: 'optimizer:context',
  versions: 'optimizer:versions',
} as const;

const MAX_VERSIONS = 50;

function isClient(): boolean {
  return typeof window !== 'undefined';
}

export function saveDocument(doc: Document): void {
  if (!isClient()) return;
  localStorage.setItem(KEYS.document, JSON.stringify(doc));
}

export function loadDocument(): Document | null {
  if (!isClient()) return null;
  try {
    const raw = localStorage.getItem(KEYS.document);
    return raw ? (JSON.parse(raw) as Document) : null;
  } catch {
    return null;
  }
}

export function saveContext(ctx: ProjectContext): void {
  if (!isClient()) return;
  localStorage.setItem(KEYS.context, JSON.stringify(ctx));
}

export function loadContext(): ProjectContext | null {
  if (!isClient()) return null;
  try {
    const raw = localStorage.getItem(KEYS.context);
    return raw ? (JSON.parse(raw) as ProjectContext) : null;
  } catch {
    return null;
  }
}

export function saveVersions(versions: Version[]): void {
  if (!isClient()) return;
  const capped = versions.slice(-MAX_VERSIONS);
  localStorage.setItem(KEYS.versions, JSON.stringify(capped));
}

export function loadVersions(): Version[] {
  if (!isClient()) return [];
  try {
    const raw = localStorage.getItem(KEYS.versions);
    return raw ? (JSON.parse(raw) as Version[]) : [];
  } catch {
    return [];
  }
}
