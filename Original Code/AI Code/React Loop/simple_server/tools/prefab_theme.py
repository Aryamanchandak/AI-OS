"""
prefab_theme.py — Shared "React Loop" visual theme for Prefab UIs.

Recreates the dark, terminal/monospace aesthetic of the React Loop frontend
(frontend/static/index.html) so any Prefab surface the agent renders matches
the rest of the app:

  - near-black background (#0d0e10) with a faint grid overlay
  - JetBrains Mono everywhere
  - mint accent (#5cffc3) driving primary buttons / focus rings
  - 0.5px hairline borders, 6px radius, translucent panel surfaces
  - uppercase micro-labels with wide letter-spacing

Used by the generative-UI tool (generative_ui.render_ui) — it is injected onto
the agent-authored PrefabApp after capture, so the agent never has to think
about styling; it just composes structure and this makes it look native.

This module defines no MCP tools; it is safe for the tools/ auto-import loop.
"""

from prefab_ui.themes import Theme

# ── COLOR TOKENS (mirrors React Loop's CSS variables) ────────────────────────
# Identical in light_css and dark_css so the look holds regardless of how the
# host toggles color scheme (same approach as Prefab's built-in Presentation).
_VARS = (
    " --radius: 6px;"
    " --background: #0d0e10;"
    " --foreground: rgba(245,248,246,0.84);"
    # Panels / cards
    " --card: #111318;"
    " --card-foreground: rgba(245,248,246,0.84);"
    " --popover: #151820;"
    " --popover-foreground: rgba(245,248,246,0.84);"
    # Muted + secondary surfaces
    " --muted: #151820;"
    " --muted-foreground: rgba(245,248,246,0.42);"
    " --secondary: #151820;"
    " --secondary-foreground: rgba(245,248,246,0.58);"
    # `accent` here is Prefab's hover/surface token (NOT the mint highlight)
    " --accent: rgba(255,255,255,0.035);"
    " --accent-foreground: rgba(245,248,246,0.84);"
    # Borders / inputs
    " --border: rgba(255,255,255,0.10);"
    " --input: rgba(255,255,255,0.14);"
    # Mint highlight — primary buttons, focus rings
    " --primary: #5cffc3;"
    " --primary-foreground: #0b0f0d;"
    " --ring: rgba(92,255,195,0.55);"
    # Status colors from React Loop
    " --destructive: #ff6b7a;"
    " --success: #8cff8c;"
    " --warning: #ffcf66;"
    " --info: #5cffc3;"
    # Charts (mint + supporting hues)
    " --chart-1: #5cffc3;"
    " --chart-2: #8cff8c;"
    " --chart-3: #ffcf66;"
    " --chart-4: #ff6b7a;"
    " --chart-5: #7dd3fc;"
)

# ── FREEFORM CSS (font, grid background, component overrides) ─────────────────
_CSS = """\
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&display=swap');

/* App root — near-black canvas with a faint grid, JetBrains Mono base */
.pf-app-root {
  min-height: 100vh;
  max-width: 64rem;
  margin: 0 auto;
  padding: 1.5rem;
  color: rgba(245,248,246,0.84);
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.65;
  background-color: #0d0e10;
  background-image:
    linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px);
  background-size: 44px 44px;
}

/* Force the mono face onto rendered components (don't trust --font to inherit) */
.pf-app-root,
.pf-app-root button,
.pf-app-root input,
.pf-app-root textarea,
.pf-app-root select,
.pf-card, .pf-table, .pf-badge, .pf-input, .pf-button,
.pf-heading, .pf-text, .pf-muted, .pf-metric {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* Cards — translucent panel, hairline border, deep shadow */
.pf-card {
  background: rgba(17,19,24,0.78);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 18px 60px rgba(0,0,0,0.28);
}

/* Headings — tighter, lighter weight to match the frontend */
.pf-heading {
  color: rgba(245,248,246,0.90);
  font-weight: 500;
  letter-spacing: 0.01em;
}

/* Muted text — the uppercase micro-label treatment */
.pf-muted {
  color: rgba(245,248,246,0.32);
  font-size: 10px;
  letter-spacing: 0.04em;
}

/* Inputs / selects / combobox / textarea — recessed translucent fields */
.pf-input,
.pf-select-trigger,
.pf-combobox-trigger,
.pf-textarea {
  background: rgba(255,255,255,0.025) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  color: rgba(245,248,246,0.84) !important;
}
.pf-input:focus,
.pf-select-trigger:focus,
.pf-combobox-trigger:focus,
.pf-textarea:focus {
  border-color: rgba(92,255,195,0.34) !important;
  box-shadow: 0 0 0 3px rgba(92,255,195,0.05) !important;
  outline: none !important;
}
.pf-input::placeholder,
.pf-textarea::placeholder { color: rgba(245,248,246,0.32); }

/* Primary buttons — mint, uppercase, wide tracking (React Loop "Run" button) */
.pf-button-variant-default {
  background: rgba(92,255,195,0.10);
  color: #5cffc3;
  border: 1px solid rgba(92,255,195,0.28);
  text-transform: uppercase;
  letter-spacing: 0.10em;
  font-size: 11px;
  font-weight: 600;
}
.pf-button-variant-default:hover {
  background: rgba(92,255,195,0.16);
  border-color: rgba(92,255,195,0.45);
}

/* Secondary / outline buttons — ghost style */
.pf-button-variant-outline,
.pf-button-variant-secondary {
  background: transparent;
  color: rgba(245,248,246,0.58);
  border: 1px solid var(--border);
}
.pf-button-variant-outline:hover,
.pf-button-variant-secondary:hover {
  color: rgba(245,248,246,0.84);
  border-color: var(--input);
}

/* Separators — hairline */
.pf-separator { background: var(--border); }

/* Badges — pill, uppercase, tinted */
.pf-badge {
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 9px;
  font-weight: 600;
  padding: 0.25em 0.7em;
}

/* Metric tiles — mint value, muted uppercase label */
.pf-metric-value { color: rgba(245,248,246,0.92); }
.pf-metric-label {
  color: rgba(245,248,246,0.32);
  text-transform: uppercase;
  letter-spacing: 0.10em;
  font-size: 9px;
}

/* Tables — hairline rows, tabular numerals, mint hover */
.pf-table-cell {
  font-variant-numeric: tabular-nums;
  color: rgba(245,248,246,0.72);
}
.pf-table-row { border-color: var(--border); }
.pf-table-row:hover { background: rgba(92,255,195,0.05); }

/* Code blocks — recessed, mint text */
.pf-code {
  background: rgba(0,0,0,0.28);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: rgba(245,248,246,0.72);
}
"""

REACT_LOOP_THEME = Theme(
    mode="dark",
    light_css=_VARS,
    dark_css=_VARS,
    css=_CSS,
)
