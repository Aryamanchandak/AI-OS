# Step 2a: Keep Only the Providers You Use

## Why
The gateway sets up Gemini (with up to 10 keys) and five free-tier services you don't use: Groq, Cerebras, NVIDIA, OpenRouter and GitHub. It also invents six provider names that encode a model tier, such as `anthropic-sonnet` and `openai-mini`. You use Claude, GPT and the local Ollama models; Together comes in step 7.

**A spend bug found while planning this step.** `config/pricing.yaml` has no entry for the GPT models the gateway uses by default (`gpt-5.4-nano`, `gpt-5.4-mini`, `gpt-5.5`), so **every GPT call is recorded as costing $0**. The Claude defaults (`claude-sonnet-4-6`, `claude-opus-4-8`) have no exact entry either. They fall back to a generic "any Claude model" price, which is wrong for Opus.

## Definition of done
- The provider list contains only `anthropic`, `openai` and the local Ollama entries from `config/local_models.yaml`.
- Each profile in `config/profiles.yaml` names a real provider plus a model, and every model it names has a correct price entry.
- The full test suite passes, and you've seen the output.

## Decisions already made
- Remove Gemini entirely: the adapter, the context cache, the multi-key setup and its prices.
- Remove all five free-tier services.
- Keep the local Ollama models: `phi4`, `gemma4` and `nomic-embed-text`.
- Collapse the tiers: one `anthropic` entry and one `openai` entry, with the model chosen by the profile or the request.

## Open questions (answer before the step starts)
1. **Which exact models?** Today's defaults are `claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-8`, `gpt-5.4-nano`, `gpt-5.4-mini` and `gpt-5.5`, but the price file lists `claude-sonnet-5`, `claude-opus-5` and `gpt-5.6-*`. Tell me which models you actually want.
2. **The prices for those models.** I'll take them from Anthropic's and OpenAI's pricing pages on the day, and show you the page and date for each. Confirm before I write them in.
3. **The default model**, used when a request names no profile and no model.

## Tests first
- **Registry test:** with only `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` set, the provider list is exactly `anthropic`, `openai` plus the Ollama entries. Setting `GEMINI_API_KEY` or `GROQ_API_KEY` adds nothing.
- **Model choice test:** a request using the `anthropic` provider with model `claude-haiku-4-5` sends that model to Anthropic. Use the existing fake HTTP transport in `tests/test_llm_providers.py`.
- **Pricing test:** every model named in `config/profiles.yaml`, and every default model, has a price whose source is a real entry, not the "unpriced" fallback.

## Files changed

| File | Change |
|---|---|
| `src/gateway/llm/providers/gemini/` (`__init__.py`, `schema.py`, `context_cache.py`, `README.md`) | **Delete the folder** |
| `src/gateway/llm/providers/registry.py` | Remove Gemini and `COMPATIBLE`/`DEFAULT_MODELS`. Register one `anthropic` and one `openai` provider with a default model each. |
| `src/gateway/llm/providers/capabilities.py` | Remove the Gemini, Cerebras and `COMPATIBLE_PROVIDERS` branches. Change the `startswith(("openai-", "anthropic-"))` check to the new names. |
| `src/gateway/llm/providers/openai_compatible/` | **Keep for now.** Together uses this format (step 7), and step 6 replaces all adapters anyway. |
| `src/gateway/llm/providers/README.md` | Remove the Gemini and free-tier rows. Describe the new names. |
| `config/profiles.yaml` | `provider: anthropic-sonnet` → `provider: anthropic` (same for `anthropic-haiku`). Check every model name. |
| `config/pricing.yaml` | Remove the Gemini, Groq, Cerebras, NVIDIA, OpenRouter and GitHub entries, patterns and the old per-provider table. Add correct entries for the chosen models. |
| `config/cache.yaml` | Remove the Gemini mention, or leave it if step 2b deletes the file anyway |
| `tests/test_llm_providers.py` | Remove the Gemini and Groq/free-tier tests. Update the tier names in the remaining tests. |
| `contracts/openapi.json` | Regenerate, only if a route description changed |

## Test files to delete
- None as whole files.
- **Test functions** inside `tests/test_llm_providers.py` that exercise only Gemini or the free-tier services. They'll be listed by name at the start of the session.

## Not in this step
- Replacing the adapters with any-llm (step 6).
- Adding Together (step 7).

## Verification
1. Run `.venv/bin/pytest -q` before starting, and record the result.
2. Add the new tests and confirm they fail.
3. Make the changes. Run `.venv/bin/pytest -q`; all should pass. Show the output.
4. Run `grep -rni "gemini\|groq\|cerebras\|nvidia\|openrouter\|anthropic-sonnet\|openai-mini" src tests config`. Expect no matches.

## Commit
```
git add -A .                                          # stage every change in gateway/
git commit -m "Shrink step 2a: keep only Claude, GPT and local providers; fix prices"   # save the snapshot
```
