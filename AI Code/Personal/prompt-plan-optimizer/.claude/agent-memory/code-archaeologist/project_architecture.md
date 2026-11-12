---
name: prompt-plan-optimizer architecture
description: Core architecture of the prompt-plan-optimizer project — modules, live vs orphaned code, and critical bugs
type: project
---

This is a Next.js 14 App Router project for iterating on AI prompts and technical plans using Claude as the backend.

**The codebase is mid-refactor with two parallel implementations:**

1. `optimizer.jsx` (project root) — the original monolith prototype. Contains inline duplicates of all lib logic plus a scaffolding UI. NOT routed by Next.js. Calls Anthropic directly from the browser (broken in production). Reference/prototype only.

2. `lib/` modules — the clean TypeScript refactor: `types.ts`, `claude.ts`, `prompts.ts`, `operations.ts`, `diff.ts`, `versioning.ts`, `storage.ts`. These are complete and type-safe but NOT YET wired to any live Next.js page.

3. `app/page.tsx` — currently just a backend smoke test ("Phase A: backend layer only"). Calls `/api/claude` directly without using any lib modules.

4. `app/api/claude/route.ts` — server-side proxy that keeps ANTHROPIC_API_KEY server-only. All production Claude calls must go through here.

**Known bugs:**
- `optimizer.jsx` line ~896: version snapshot uses closure `conflicts` (stale) instead of freshly-detected `newConflicts`. Plan mode version history stores one-edit-stale conflict data.
- `lib/operations.ts` substring assertion: `output.includes(assertion.spec.text ?? '')` — empty text always passes must_include.
- Jaccard similarity diverges between optimizer.jsx (Set-based, correct) and lib/operations.ts (Array-based, inflated).
- `lib/versioning.ts` classifyTestChanges: new tests with no prior result labeled 'unchanged' instead of 'new'.

**Why:** Build is in Phase A (backend verified). Phase B is the production three-pane UI that wires lib/ into app/page.tsx.
**How to apply:** When suggesting UI work, build on top of lib/operations.ts functions. Do not import optimizer.jsx into any Next.js route.
