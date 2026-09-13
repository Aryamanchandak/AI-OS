# Unified UI plan (UI only)

## Context

The shell (`shell/`) is the one unified UI. GLC is deliberately staying a
standalone FastAPI service on its own port until the already-drafted
`Gateway to do/GLC and ingestion gateway migration/` plan sequence actually
moves it — Plan 02 explicitly puts "importing GLC runtime modules" and
"redesigning the frontend" out of scope for now, and Plan 05 ("GLC channels
and voice", section E) is the place that decides which GLC static pages
become real React shell pages and how their settings/config surfaces get
exposed. This plan does not re-decide any of that. It covers only what the
shell itself does today, with no backend or `glc_v5` file changes.

## Scope

Add a nav entry to the shell that reaches GLC's existing UI at its existing
address. Nothing else moves, nothing else gets rewritten, no gateway code
changes, no edits to `glc_v5/static/*.html`.

### `shell/src/components/AppShell.tsx`

Add a real link next to `01 Ingestion`, pointing at GLC's own address
(configurable, not hardcoded to a same-origin path, since GLC is not mounted
under the gateway):

```tsx
<a href="/ingestion"><span>01</span> Ingestion</a>
<a href={GLC_BASE_URL}><span>02</span> GLC</a>
<span className="future">Finance</span>
...
```

`GLC_BASE_URL` comes from a build-time/runtime env var (e.g.
`VITE_GLC_BASE_URL`, default `http://127.0.0.1:8111/` for local dev) rather
than a literal string, so it keeps working unmodified once GLC's real address
changes (e.g. if it moves behind the gateway later, or runs on a different
host in a deployment) — that update happens in one place, not by touching
this plan again.

This is a plain full-page `<a>` (the shell has no client-side router), so it
navigates cross-origin to GLC's existing standalone pages exactly as they run
today — unmodified.

## Explicitly not in this plan

- Mounting `glc.main:app` anywhere inside `gateway/main.py` — that's the
  Gateway migration plan's decision to make and sequence (Plans 02–05).
- Editing `glc_v5/static/*.html` (path-prefixing, or anything else) — those
  pages are unmodified and keep serving from GLC's own origin as-is. Which of
  them get rewritten as real shell screens (dashboard, observability, and
  especially the channel-settings/secrets UI in `channels.html`) is Plan 05's
  "E. UI and administration" decision, not this one.
- Docker/EC2/Hetzner packaging — deployment/cutover is Plan 07's territory,
  once there's actually one thing to deploy instead of two.

## Open question worth flagging to the gateway migration plans (not decided here)

`channels.html` requires manually pasting the install token from
`~/.glc/install_token` — that's real, currently-necessary settings/config
surface, not cosmetic. When Plan 05 decides which GLC pages become shell
screens, this is the one most worth turning into a proper screen rather than
linking out to, since it's the one an operator actually needs regularly.
Noting it here only so it isn't lost; the decision belongs in Plan 05's
comments section.

## Verification

1. `cd shell && npm run dev` (or build), confirm the new GLC nav link renders.
2. With GLC running standalone (`cd glc_v5 && uv run glc serve`, port 8111),
   click the link — confirm it navigates to GLC's dashboard unchanged.
3. Confirm `/ingestion` and everything else in the shell is untouched.
