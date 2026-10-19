# Step 7: Add Together.ai

Outline only. Detailed when step 6 is done.

**Why.** You want Together alongside Claude and GPT. After step 6, adding a provider should be config, not code; this step proves it.

**Done when.** With `TOGETHER_API_KEY` in `.env`, a Together profile returns a correct answer, logged with a correct non-zero cost. A new Together golden case passes along with all earlier ones. No new Python beyond config; if any-llm needs some, stop and tell you.

**Decided.** Use any-llm's built-in `together` provider (the `together` extra).

**Answer before starting.**
1. What is Together for: which jobs and which models?
2. Prices from Together's pricing page on the day, shown to you with page and date.
3. Embeddings on Together? If yes, **never mix them with your nomic vectors in one collection**; vectors from different models can't be compared.
