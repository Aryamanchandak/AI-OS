# Step 2c: Remove Unused Request Features; Budgets by Agent and Session

## Why
Several request options either do nothing or do the wrong thing:
- **`batch: true` is a bug.** It records the cheaper batch price, but the call is sent as a normal, full-price one, so recorded spend is too low.
- **`auto_route`, `cost_quality_tradeoff` and `escalate`** are ignored. They're left over from a router that was never built.
- **`/chat/batch`** runs many calls in parallel without anyone measuring a need for it.
- **`/vision`** duplicates `/chat`.
- **The gateway downloads images from links** (`security/ssrf.py`, ~145 lines). That means fetching from the internet, and it depends on private, undocumented parts of the httpx library.
- **Budgets track five levels.** Tenant, project and user are for multi-customer setups; you need agent and session.

## Definition of done
- The `batch`, `auto_route`, `cost_quality_tradeoff` and `escalate` fields, `/chat/batch`, `/vision` and `ssrf.py` are gone.
- A request with an image link is rejected with a clear message: "send the image as a data: URL".
- An image sent to a model that can't read images is rejected with a clear message.
- Budgets, and the cost-by-principal route, know only `agent` and `session`.
- The full test suite passes, and you've seen the output.

## Decisions already made
- Images go to `/chat` with a profile; `/vision` goes. You said "ok".
- Image transcription becomes a profile in `config/profiles.yaml`, for example `image-transcription-v1`. The model is to be confirmed (see open question 2).
- Budgets: agent and session only.
- Real batching comes back later as its own feature (README, "Later").

## Open questions (answer before the step starts)
1. **Your image-approach chat.** Does it confirm that every image reaches the gateway as bytes (a `data:` URL), never as a link? If not, `ssrf.py` stays and this step skips it.
2. **The model for the `image-transcription-v1` profile:** local `gemma4:12b` (free, private) or Claude Haiku (cheap, cloud)? It can be changed later with one line.

## Tests first
- A `ChatRequest` with `batch`, `auto_route`, `cost_quality_tradeoff` or `escalate` is rejected as an unknown field. Alternatively the field is simply dropped from the contract; decide at the start of the session.
- `POST /api/llm/chat/batch` and `POST /api/llm/vision` return 404 ("not found").
- An `image_url` with an `https://` link returns 400 ("bad request") with the data-URL message, and no download is attempted.
- An image sent to a provider whose capabilities say `vision: false` returns 400. This finally puts `content_has_image` to use.
- `POST /api/llm/budget` with `principal: "tenant:*"` returns 400 ("bad request"). `agent:*` and `session:*` work.
- The `image-transcription-v1` profile resolves to the chosen model.

## Files changed

| File | Change |
|---|---|
| `src/gateway/llm/models.py` | Remove `batch`, `auto_route`, `cost_quality_tradeoff`, `escalate`, `tenant`, `project`, `user`, `BatchChatRequest` and `VisionRequest`. Update the `BudgetSetRequest` docstring. |
| `src/gateway/llm/orchestration/validation.py` | Drop the `auto_route` check. Add "an image needs a vision-capable model", using `content_has_image`. |
| `src/gateway/llm/orchestration/normalization.py` | Stop downloading links. Reject `http(s)` image links with the data-URL message. |
| `src/gateway/llm/orchestration/budget.py`, `finalization.py` | Drop `batch=` from the pricing calls. In `finalization.py`, stop using `request.user` for the audit user; use the agent. |
| `src/gateway/llm/economics/pricing.py` | Drop the `batch` argument and `batch_multiplier`. It returns with real batching. |
| `src/gateway/llm/economics/meter.py` | `DIMENSIONS = ("agent", "session")` |
| `src/gateway/llm/economics/budget.py` | Follows the new `DIMENSIONS`. Remove the unused `projection`, `alerts` and `load_overrides` setting (runtime overrides stay on). |
| `src/gateway/llm/api/routes.py` | Remove `/chat/batch` and `/vision`. The cost-by-principal route uses only the two dimensions. |
| `src/gateway/llm/api/preflight.py` | Drop `escalate=False` |
| `src/gateway/security/ssrf.py`, `src/gateway/security/README.md` | **Delete**, and the `security/` folder if it's left empty |
| `config/budgets.yaml` | Remove the `projection` and `alerts` sections and the tenant/user examples |
| `config/pricing.yaml` | Remove the `batch_multiplier` lines |
| `config/profiles.yaml` | Add `image-transcription-v1` |
| `src/gateway/llm/profiles/README.md`, `src/gateway/llm/api/README.md`, `src/gateway/llm/economics/README.md` | Update the wording |
| `tests/test_llm_contract.py` | Remove the `/v1/chat/batch` and `/v1/vision` map entries. Add the new tests. |
| `tests/test_platform_security_control.py` | Remove the SSRF tests |
| `tests/test_restored_contracts.py`, `tests/test_llm.py`, `tests/test_llm_orchestration.py` | Adjust the budget and routing-field tests to the two dimensions |
| `contracts/openapi.json` | Regenerate |

## Test files to delete
- None as whole files.
- **Test functions** for SSRF in `tests/test_platform_security_control.py`, and for tenant/project/user budgets in the files above. They'll be listed by name at the start of the session.

## Not in this step
- The ledger's tenant/project/user columns (step 4).
- Real batching (later feature).
- The concurrency cap of 32 (step 6 moves it into config).

## Verification
1. Run `.venv/bin/pytest -q` before starting, and record the result.
2. Add the new tests and confirm they fail.
3. Make the changes. Regenerate `contracts/openapi.json`. Run `.venv/bin/pytest -q`; all should pass. Show the output.
4. Run `grep -rn "auto_route\|cost_quality_tradeoff\|escalate\|batch_multiplier\|ssrf\|VisionRequest\|tenant" src tests config`. Expect no matches, apart from the ledger columns that are left for step 4.

## Commit
```
git add -A .                                                   # stage every change in gateway/
git commit -m "Shrink step 2c: remove unused request features; budgets by agent+session"   # save the snapshot
```
