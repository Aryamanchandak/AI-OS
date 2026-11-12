# `tax/classifier.py`

**Lines:** 260

## Purpose

Defines the classification system for the tax module. There is a `Classifier` Protocol, two concrete implementations (`RuleBasedClassifier` and `LocalLLMClassifier`), and a factory function (`get_active_classifier`) that reads `tax_settings` to return whichever is active. The module is the mechanism by which individual payments get assigned to user-defined buckets.

## Entry Points

- `get_active_classifier(conn)` — called by `routes.py` for every context fetch and classify operation.
- `RuleBasedClassifier(conn)` — instantiated directly in `routes.py` for auto-classify pass and for `learn()` calls.

## Classification Logic — `RuleBasedClassifier.suggest()`

Five lookup levels, first hit returns:

| Level | Lookup | Confidence returned |
|---|---|---|
| 1 | Exact VPA match in `category_rules` | 1.0 |
| 2 | Exact merchant name match in `category_rules` | 0.9 |
| 3 | Substring overlap on name (bidirectional `LIKE`) | 0.6 |
| 4 | Mode category across ≥2 past `payments` rows for same VPA/name | 0.5 |
| 5 | No match | 0.0, bucket=None |

Confidence thresholds:
- `CONFIDENCE_AUTO_APPLY = 0.85` → levels 1 and 2 trigger silent auto-classify after upload
- `CONFIDENCE_TRIAGE = 0.40` → levels 3 (0.6) and 4 (0.5) show as suggestions in triage UI
- Level 5 (0.0) shows no suggestion

## `LocalLLMClassifier.suggest()` Flow

1. Run `RuleBasedClassifier.suggest()` first.
2. If rule confidence ≥ 0.85, return the rule result immediately (no LLM call).
3. If no endpoint configured, return rule result.
4. POST to `{endpoint}/v1/chat/completions` with `temperature=0.0`, `max_tokens=16`, asking for one bucket name.
5. Validate response against known active buckets (case-insensitive). If valid, return with confidence 0.7.
6. If LLM returns an unknown bucket, or any network/parse error, return the rule result.

## Key Classes / Functions

| Name | What it actually does |
|---|---|
| `Suggestion` | Dataclass: bucket name (or None), confidence float, reason string |
| `Classifier` | Protocol (structural typing) — defines `suggest()` and `learn()` signatures |
| `RuleBasedClassifier.suggest()` | 5-level confidence-ranked lookup; first hit wins |
| `RuleBasedClassifier.learn()` | Upserts to `category_rules` for both VPA and name keys |
| `LocalLLMClassifier.suggest()` | Rules-first wrapper; calls LLM only for uncertain rules |
| `LocalLLMClassifier.learn()` | Delegates entirely to `RuleBasedClassifier.learn()` |
| `get_active_classifier(conn)` | Factory: reads `tax_settings.mode`; returns Rule or LLM classifier |

## Design Decisions

- LLM suggestions are capped at confidence 0.7, which is below `CONFIDENCE_AUTO_APPLY` (0.85). This means LLM suggestions are **never** auto-applied silently — they always require a user confirmation click.
- Both VPA and name rules are written on every `learn()` call, even if one of them is None.
- All learning goes into `category_rules`; the LLM is only for suggestion, never for rule storage.

## Known Gaps / Risks

- **Level 4 minimum threshold:** Requires ≥2 historical transactions for the same merchant before it provides a suggestion at confidence 0.5.
- **Substring match false positives:** The bidirectional LIKE in level 3 can match unrelated merchants with short common substrings. There is no minimum length guard on the key value.
- **LLM output not sanitised:** Only validated against known buckets. If the model returns a bucket name with non-trivial whitespace or different Unicode normalisation, it falls through to the rule result rather than erroring.
- `get_active_classifier` does not close the connection — the caller owns the lifecycle.
