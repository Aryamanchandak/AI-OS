# `providers/__init__.py`

Empty package marker. The file is two lines: a docstring (`"""External provider boundaries."""`) and a trailing blank line — no code, no re-exports.

It exists to make `consequence_radar.providers` an importable package and to name, in one sentence, what the subpackages underneath it are for: everything that talks to something outside the process (LLM calls, web search, HTTP fetch) lives under here, one subpackage per external boundary. The actual boundaries are the sibling subpackages: `fetch/` (HTTP page retrieval), `search/` (grounded web search via Gemini), and `model/` (LLM provider, documented separately). Callers import from `consequence_radar.providers.fetch` and `consequence_radar.providers.search` directly — nothing is re-exported at this level, so this file has no behavior to document beyond the docstring.
