# app/globals.css — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 28
**Language:** CSS (Tailwind CSS directives)

---

## What This File Does (Plain English)

This file is the global stylesheet. It injects Tailwind's base styles, component styles, and utilities, then defines light/dark color tokens via CSS custom properties on `:root`, and sets the default body font and a text-balance utility. It is imported once by `app/layout.tsx`.

---

## How It Actually Works

### Entry Points

Imported at the top of `app/layout.tsx`. Applied globally — every page and component inherits these styles.

### Data Flow

No runtime behavior — this is a static stylesheet processed at build time by PostCSS and Tailwind.

### State Management

None.

### Key Functions / Classes

None — this is CSS.

| Rule | What it actually does |
|---|---|
| `@tailwind base` | Injects Tailwind's Preflight CSS reset |
| `@tailwind components` | Injects any Tailwind component utilities (none defined here) |
| `@tailwind utilities` | Makes all Tailwind utility classes available |
| `:root { --background, --foreground }` | Defines light mode color tokens: white background, dark foreground |
| `@media (prefers-color-scheme: dark)` | Overrides to near-black background and light foreground in dark mode |
| `body { color, background, font-family }` | Applies the color tokens to the body and sets the font to `Arial, Helvetica, sans-serif` |
| `.text-balance` | Adds `text-wrap: balance` for balanced multi-line headings |

### External Dependencies

- `tailwindcss` — processes `@tailwind` directives at build time via PostCSS

### Error Handling

None applicable to CSS.

---

## Non-Technical Decisions Embedded in the Code

- **`font-family: Arial, Helvetica, sans-serif`** — this is the system fallback font stack, not the Geist fonts loaded in `layout.tsx`. The Geist font CSS variables (`--font-geist-sans`, `--font-geist-mono`) are defined in `layout.tsx` but never referenced here. As a result, the custom fonts are loaded but not applied.
- **`--background` and `--foreground` CSS variables are defined** but the actual pages (especially `app/page.tsx`) primarily use hardcoded Tailwind classes like `bg-gray-950` rather than `bg-background`. The tokens are effectively unused in the current codebase.
- **Dark mode is OS-preference based** (`prefers-color-scheme: dark`) rather than a user toggle. There is no class-based dark mode switch.

---

## Honest Gaps and Risks

- **Geist fonts are loaded but not used** — the CSS variable font approach in `layout.tsx` requires `var(--font-geist-sans)` to appear somewhere in CSS or as a Tailwind class. Neither happens. Remove the font loading or add `font-family: var(--font-geist-sans)` here.
- **Color tokens `--background` and `--foreground` are unused** — defined but not referenced by any component. Page-level components use Tailwind color classes directly instead.

---

## Developer Notes

This file is standard create-next-app output with minimal modifications. The only change needed is either wiring the Geist font variable to `body { font-family: var(--font-geist-sans), Arial, Helvetica, sans-serif }`, or removing the font loading from `layout.tsx` entirely. Both the font gap and the unused color tokens are cosmetic at this stage.
