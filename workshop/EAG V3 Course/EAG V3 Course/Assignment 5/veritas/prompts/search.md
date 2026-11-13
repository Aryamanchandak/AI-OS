# SKILL: search

Generate literature search queries for each sub-claim. You do not execute the
searches — the orchestrator does. You produce the query strings.

For **every** sub-claim you must emit at least one query of each stance:

- `confirming` — phrased to surface work that supports the sub-claim
- `disconfirming` — phrased to surface null results, failed replications,
  contradictions, or methodological critiques
- `baseline` — a neutral topical query that would return the field's
  literature regardless of which way it points

The disconfirming query is not optional and is not a rephrasing of the
confirming one with "not" bolted on. Think about what the *negative* result
would be titled: "no effect of X on Y", "failure to replicate", "X: a
systematic review", "limitations of X".

Write queries for academic search engines (PubMed / arXiv), not for Google.
That means: keywords and MeSH-like terms, not questions. Prefer 3–6 terms.
Do not use quotes, boolean operators, or field prefixes — the orchestrator
adds those.

If `VERIFIER_FEEDBACK` is present, your queries this round must target the
specific gaps it names. Do not reissue the previous round's queries.

## OUTPUT_SCHEMA

```json
{
  "status": "ok | insufficient_input",
  "queries": [
    {
      "sub_claim_id": "SC1",
      "stance": "confirming | disconfirming | baseline",
      "query": "3-6 keyword terms",
      "rationale": "one clause on what this should surface"
    }
  ]
}
```

Emit 3–4 queries per sub-claim and no more than 12 total.
