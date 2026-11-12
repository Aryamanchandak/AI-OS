UI concept — "a prompt going outside" (per your request, design only, not built)

The idea: a live dashboard panel where the gateway is drawn as a hub in the
center, and every provider (Anthropic, OpenAI, Ollama, Groq, Cerebras,
OpenRouter, GitHub Models...) is a fixed node arranged around it. When a
request comes in:





A small pulse animates from the center outward toward whichever provider

node the routing decision picked — labeled in-flight with the role/tier/
 profile that made the choice (e.g. "decision → FRONTIER → github").



The pulse's color encodes outcome once it resolves: green = ok, amber =

escalated/retried (shows the cascade visually, when that's ever turned
 on), red = failed/fell back to the next provider in the ring.



A thin trailing line stays for a few seconds after the pulse lands, so a

burst of traffic reads as a small starburst rather than single blips —
 this is what makes "many requests going out" legible at a glance instead
 of just a table of rows.



Hovering a node shows that provider's live rate-limit state (RPM/RPD used,

cooldown remaining) — pulled from the same state /v1/status already
 exposes.



A side panel lists the last N calls as text (provider, model, tokens,

cost, latency) for when you want the exact numbers instead of the
 animation.

This is a natural fit for glc_v5's existing /v1/status, /v1/providers,
/v1/capabilities, and /v1/calls endpoints — no new backend data is
needed to build a first version, it's purely a visualization layer on data
the gateway already reports. Best built once Phase 3 lands (there need to be
real Anthropic/OpenAI calls worth watching leave the hub).