# extract.py — Technical Documentation

**Last updated:** 2026-07-23  
**Lines of code:** 241  
**Language:** Python

---

## 1. What This File Does (Plain English)

This file asks Gemini to turn one plain-English situation into a small causal map. It checks that the returned map obeys the application's structural rules and gives the model one chance to correct mistakes. It can also be run directly to print a graph for debugging.

---

## 2. The 30-Second Mental Model

`extract_graph()` sends one structured-output request, converts the parsed payload to mutable dataclasses, validates counts, endpoints, leaf rules, signs, unknown references, and acyclicity, then either returns the graph, retries once with the failures, or raises `ExtractionError`.

---

## 3. Architecture at a Glance

```text
[situation string]
       │
       ▼
[_call_model()] ──empty/unparseable──▶ [ExtractionError]
       │ dict
       ▼
[_build_graph()]
       │ Graph
       ▼
[_validate()] ──valid──▶ [return Graph]
       │ invalid
       ▼
[retry once with problem list] ──invalid──▶ [ExtractionError]
```

---

## 4. Execution Walkthrough — The Heart of This Document

### Layer 1 — The Story in Plain English

The caller provides a situation. The file checks that credentials exist, asks Gemini for the entire map in one response, and examines the result. If the map is sound it returns it immediately; if not, it tells Gemini exactly what failed and retries once. A second bad map ends the operation with a readable error.

### Layer 2 — The Same Story With More Detail

`extract_graph()` optionally accepts an injected Google client. Without one it accepts either `GEMINI_API_KEY` or `GOOGLE_API_KEY` and constructs `genai.Client()`. `_call_model()` formats `_INSTR`, uses `_SYSTEM` plus `CausalGraphOut` as a forced JSON response schema, and returns `resp.parsed.model_dump()`. `_build_graph()` converts that dictionary into dataclasses, while `_validate()` produces a list of semantic problems used as the retry nudge.

### Layer 3 — The Full Technical Reality

At import, `load_dotenv()` runs at L20–21, mutating process environment values from a local `.env` if present. `_call_model()` formats the raw situation directly into `_INSTR` at L156–162; there is no input length or emptiness check here. The Gemini call at L165–177 uses the hardcoded `gemini-2.5-flash`, JSON MIME type, `CausalGraphOut`, 8192 output tokens, and zero thinking budget. If `resp.parsed` is `None`, L178–180 raises `ExtractionError`; SDK/network exceptions pass through unchanged.

`_build_graph()` at L70–96 assumes the dumped payload has all expected list and field keys. Pydantic normally guarantees that, but a fake client or direct helper call can trigger `KeyError`/`TypeError`. `_validate()` at L99–153 checks node and outcome counts, edge references, nonblank mechanisms, signs, outcome leaf status, DAG status, and unknown count/references. It does not verify root reachability, intervention indegree, maximum depth, unique IDs, unknown ID uniqueness, or that unknown questions are genuinely binary.

`extract_graph()` starts at L185. Credentials are required only when no client is injected (L191–197). The first result is returned at L203–204 when `problems` is empty. Otherwise L206–213 makes a complete second model call with a user-level nudge listing failures; if validation still fails, L214–217 raises a combined `ExtractionError`. The CLI path at L221–241 uses argv text or a hardcoded RBI example, then prints nodes, edges, and unknowns.

---

## 5. Data Flow — What Comes In, What Comes Out

Plainly, text enters and a checked causal graph leaves.

With detail, `situation: str` becomes `"Map the causal graph...\n\nSituation: ..."`; Gemini returns a `CausalGraphOut`; `model_dump()` creates nested dictionaries; `_build_graph()` creates a `Graph`.

For example, `"RBI cuts the repo rate by 50bp"` is embedded at L158. A parsed node dictionary `{"id":"n1","label":"repo rate","node_type":"intervention"}` becomes `Node(..., sign=0, magnitude="med")` at L74–77. Edge `sign` is explicitly coerced with `int()` at L82. Validation returns `[]` or strings such as `"edge src 'x' is not a node"`, and the public output is a mutable `Graph`.

---

## 6. State & Side Effects

The normal operation changes no application database because none exists, but it reads environment configuration and makes network requests.

Module-level state consists of `MODEL`, `_SYSTEM`, and `_INSTR`. `load_dotenv()` may update process environment at import. Each `_call_model()` makes one remote generation request; `extract_graph()` may make two. The CLI prints to stdout.

No call is cached or persisted, and retries are not idempotently keyed. A slow request blocks the caller. The returned graph lives only in memory. Environment keys are read at L193 and never logged by this file.

---

## 7. Control Flow Map

The main decisions are whether a client was supplied, whether credentials exist, whether parsing succeeded, and whether validation passed before and after retry.

Branches include `if client is None` (L191), credential absence (L193), `if parsed is None` (L179), first validation success (L203), and second validation failure (L214). Validation contains count, membership, blank-text, sign, leaf, DAG, and unknown-reference branches.

The precise public flow is: injected client skips credential checks; absent client plus absent both key names raises before a request; first valid graph returns; first invalid graph always consumes one retry; second valid graph returns; second invalid graph raises. `_validate()` accumulates all detected failures rather than returning early.

---

## 8. Function & Class Reference

| Name | Lines | What it actually does (2–3 honest sentences) |
|---|---|---|
| `ExtractionError` | L64–67 | Labels selected extraction failures. It does not wrap all Google SDK, Pydantic, or conversion errors. |
| `_build_graph()` | L70–96 | Copies a dumped structured response into mutable dataclasses. It assumes keys and list shapes are already valid. |
| `_validate()` | L99–153 | Accumulates several graph-contract violations and uses NetworkX for cycle detection. It validates less than the full system prompt promises. |
| `_call_model()` | L156–182 | Performs one synchronous Gemini request and returns a plain dictionary. It has no timeout, retry, or exception normalization. |
| `extract_graph()` | L185–218 | Orchestrates credentials, request, conversion, validation, and exactly one corrective retry. |
| CLI entry | L221–241 | Runs live extraction and prints the returned graph for manual inspection. |

---

## 9. External Dependencies

- `python-dotenv` (L16, L21) reads `.env`; missing package prevents import.
- `google-genai` (L17–18, L165–177) performs structured generation; unavailable, slow, blocked, or rate-limited calls propagate SDK exceptions.
- Pydantic schema objects from `schema.py` define parsing expectations.
- NetworkX (L15, L138–142) validates acyclicity.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` is read at L193; injected clients bypass this check.
- The CLI reads `sys.argv` and writes stdout at L224–241.

---

## 10. Error Handling Reality

In plain English, malformed-but-parsed graphs get one repair attempt; most transport and programming failures simply escape.

`ExtractionError` handles missing credentials, an absent parsed payload, and two semantic validation failures. The Streamlit caller catches this class, but not generic SDK exceptions.

There are no `try` blocks in this module. Network errors at L165, Pydantic/SDK errors, `model_dump()` incompatibility, dictionary conversion errors, and NetworkX errors propagate. A graph can be “valid” while violating prompt-only requirements such as maximum depth or intervention indegree, creating a silent wrong-but-plausible result.

---

## 11. Non-Technical Decisions Embedded in the Code

- **Whole graph in one call** (L38–59) — prioritizes global coherence and low call count.
- **One corrective retry only** (L206–217) — bounds latency and cost but may reject recoverable outputs.
- **Hardcoded Gemini Flash model** (L34) — speed and cost are favored over configurability.
- **Thinking disabled** (L172–175) — all output budget is reserved for JSON.
- **Validation errors are fed back verbatim** (L207–211) — model repair is guided by local deterministic checks.

---

## 12. Honest Gaps and Risks

- Maximum depth three and intervention indegree zero are promised at L43–45 but never validated.
- Duplicate IDs collapse in the `node_ids` set and can make endpoint checks misleading.
- No timeout or SDK retry exists around L165–177.
- Empty or extremely long situations are accepted by `extract_graph()`.
- `extract_graph()`'s “one LLM call” docstring at L188 conflicts with its retry behavior.
- Generic request failures are not converted to `ExtractionError`, so `main.py` may show a raw Streamlit exception.

---

## 13. Developer Notes — Read Before Editing

Prompt constraints and `_validate()` are separate contracts; change both when adding graph rules. Pydantic schema changes must remain compatible with `_build_graph()`. Tests currently concentrate on propagation, so extraction changes require injected-client unit tests or live manual checks.
