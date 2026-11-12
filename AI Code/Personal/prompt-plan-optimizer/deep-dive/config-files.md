# Configuration Files — Technical Documentation

**Last updated:** 2026-05-10
**Files covered:** `package.json`, `tsconfig.json`, `tailwind.config.ts`, `postcss.config.mjs`, `.eslintrc.json`

---

## What These Files Do (Plain English)

These files define the toolchain: what packages are installed, how TypeScript compiles the project, how Tailwind generates CSS, how PostCSS processes stylesheets, and what ESLint rules apply. They are all boilerplate from `create-next-app` with minimal project-specific changes.

---

## package.json

**Lines of code:** 27

### What it actually does

Defines the project name, version, npm scripts, and dependencies.

**Scripts:**
- `dev` — starts the Next.js development server
- `build` — compiles the production bundle
- `start` — serves the production build
- `lint` — runs ESLint via Next.js

**Runtime dependencies:**
- `react: ^18`, `react-dom: ^18` — React framework
- `next: 14.2.35` — pinned Next.js version (App Router)

**Dev dependencies:**
- `typescript: ^5`, `@types/node: ^20`, `@types/react: ^18`, `@types/react-dom: ^18` — TypeScript support
- `tailwindcss: ^3.4.1`, `postcss: ^8` — CSS toolchain
- `eslint: ^8`, `eslint-config-next: 14.2.35` — linting

**Non-obvious decisions:**
- `next` is pinned to `14.2.35` (exact version) while most deps use `^` ranges. This prevents accidental Next.js upgrades.
- No Anthropic SDK (`@anthropic-ai/sdk`) is installed — the API is called via raw `fetch`, not the official SDK. This means no TypeScript types for Anthropic API responses, no built-in retry/timeout handling, and no streaming support from the SDK.
- No testing libraries — there are no unit tests for the `lib/` modules despite having a test runner concept in the app itself.
- No state management library — React `useState` only, consistent with the single-user local-only design.

---

## tsconfig.json

**Lines of code:** 28

### What it actually does

Configures TypeScript compilation for the Next.js project.

**Key settings:**
- `target: "es2017"` — output targets ES2017 (async/await compiled to generators if needed, but modern browsers support native async/await)
- `strict: true` — enables all strict checks: `strictNullChecks`, `noImplicitAny`, etc.
- `noEmit: true` — TypeScript only type-checks; Next.js's own bundler (SWC) handles actual compilation
- `moduleResolution: "bundler"` — uses Next.js/SWC resolution semantics rather than Node.js resolution
- `paths: { "@/*": ["./*"] }` — enables the `@/lib/...` import alias used across all `lib/` files
- `incremental: true` — caches type-check results in `.next/` for faster rebuilds
- `jsx: "preserve"` — JSX is not transformed by TypeScript; Next.js/SWC handles it

**Non-obvious decisions:**
- `"allowJs": true` — allows `.js` and `.jsx` files to be included. This is what enables `optimizer.jsx` to coexist without causing TypeScript errors.
- `isolatedModules: true` — each file must be compilable independently. This prevents use of `const enum` and `namespace` exports that require cross-file type information.
- The `include` array does not specifically list `optimizer.jsx` — it's covered by `**/*.tsx` (which matches `.jsx` via `allowJs`).

---

## tailwind.config.ts

**Lines of code:** 20

### What it actually does

Configures Tailwind CSS content scanning and theme extensions.

**Content paths** — Tailwind scans these globs for class names to include in the output CSS:
- `./pages/**/*.{js,ts,jsx,tsx,mdx}` — not used (project uses `app/` router, not `pages/`)
- `./components/**/*.{js,ts,jsx,tsx,mdx}` — not used (no `components/` directory exists)
- `./app/**/*.{js,ts,jsx,tsx,mdx}` — the actual source location

**Theme extensions:**
- `colors: { background: "var(--background)", foreground: "var(--foreground)" }` — exposes the CSS custom properties from `globals.css` as Tailwind color utilities (`bg-background`, `text-foreground`). These utilities are defined but not used by any component.

**Plugins:** none.

**Non-obvious decisions:**
- The `pages/` and `components/` globs in the content array are dead — they match no files. Tailwind won't incorrectly include/exclude classes, but the dead globs are noise.
- `optimizer.jsx` uses inline style objects, not Tailwind classes — so even though Tailwind scans `app/`, it won't pick up any classes from `optimizer.jsx` (which isn't in `app/`).

---

## postcss.config.mjs

**Lines of code:** 8

### What it actually does

Configures PostCSS to run the Tailwind CSS plugin. Minimal boilerplate — the only plugin is `tailwindcss`. PostCSS is invoked automatically by Next.js during CSS processing.

---

## .eslintrc.json

**Lines of code:** 3

### What it actually does

Extends two ESLint rulesets:
- `next/core-web-vitals` — Next.js recommended rules plus Core Web Vitals checks (image optimization, font optimization, etc.)
- `next/typescript` — TypeScript-aware Next.js ESLint rules

No custom rules are added. Running `npm run lint` applies these two rulesets to all source files.

**Non-obvious decisions:**
- `optimizer.jsx` is a `.jsx` file in the project root. ESLint will lint it if it matches the default `eslint-config-next` patterns, which typically cover all `.js`/`.jsx`/`.ts`/`.tsx` files in the project.

---

## Honest Gaps and Risks (Configuration-Level)

- **No Anthropic SDK** — raw `fetch` to Anthropic means no typed response objects, no retry on 429, no streaming. If the Anthropic API contract changes, failures will appear at runtime rather than compile time.
- **No test framework** — there are no unit tests for `lib/operations.ts`, `lib/diff.ts`, or any other module. The application tests prompts via its own test-runner UI, but the library code itself is untested.
- **Dead content globs in `tailwind.config.ts`** — `pages/` and `components/` paths scan nothing. Harmless but indicative that this config was not customized from the create-next-app default.
- **`next` is pinned but other deps use `^` ranges** — a `npm install` could pull in a new major version of React or TypeScript with breaking changes, while Next.js stays locked. Normally Next.js pinning is the right call, but the asymmetry is worth noting.

---

## Developer Notes

The `@/*` path alias is load-bearing for all `lib/` imports across the codebase. It is defined in `tsconfig.json` and resolved by Next.js/SWC at bundle time. If you add a new top-level directory and want `@/newdir/...` imports, you do not need to change the tsconfig — the `"@/*": ["./*"]` pattern already covers it. To install the Anthropic SDK and get typed responses, run `npm install @anthropic-ai/sdk` and update `lib/claude.ts` to use the SDK's `Anthropic` client rather than raw `fetch`.
