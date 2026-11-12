# Phi-4 document-segmentation profile — 2026-07-29

The gateway now exposes one dedicated local chat route:

```text
document-segmentation-v1
  -> phi4-local
  -> phi4:14b-q4_K_M
```

`phi4-local` is built only when `ENABLE_PHI4_CHAT=1`. Its model tag is fixed in
the provider registry and does not read `OLLAMA_MODEL`; that variable continues
to belong only to the optional `gemma` provider. The profile has no fallback,
so a disabled, missing, or unavailable Phi-4 fails instead of selecting a
hosted provider.

`GET /v1/chat/profiles/{profile}` and
`LLM.resolve_chat_profile(profile)` expose the resolved provider and exact
model. `/v1/providers` also reports chat profiles and availability.

The Ollama adapter now translates native `done_reason="length"` to the
gateway contract `stop_reason="max_tokens"`.

Offline verification:

```text
.venv/bin/python -m pytest -q \
  tests/test_provider_registry.py tests/test_tool_translation.py

13 passed
```

No model was downloaded and no live model call was made by this change.
