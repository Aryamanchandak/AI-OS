# Veritas — a scientific claim verification agent

**EAG V3 · Assignment 5**

Give it a scientific claim. It decomposes the claim into checkable sub-claims,
searches PubMed and arXiv (including deliberately for *disconfirming* evidence),
extracts structured findings from real abstracts, grades each source's
evidentiary weight, synthesizes a verdict, then adversarially audits its own
synthesis — and can send itself back for another round of evidence gathering if
the audit fails.

It is not a summarizer. It reaches a verdict, cites it, grades the citations,
and tells you its own weakest link.

> **Since this evaluation, Veritas grew a second output and a second front
> door.** An 8th skill, `compose`, turns the verdict into a full explanatory
> essay instead of a report — and a parallel pipeline (`scope` →
> `compose_topic`, reusing `search`/`fetch`/`extract`/`grade`) lets you hand
> it an open topic instead of a claim and get an essay with no verdict at
> all, just what's established and what's contested. Both are reachable from
> a Streamlit UI (`veritas/app.py`) as well as the CLI. See
> [`veritas/PLAN.md`](veritas/PLAN.md) for the roadmap and rationale; the
> architecture/run-log sections below describe the original 7-skill
> claim-verification pipeline they were evaluated against and are unchanged.

```
$ python cli.py "Creatine supplementation improves cognitive performance in sleep-deprived adults"

  Verdict    MIXED
  Confidence medium
  Sources    18 examined over 1 round(s)

  CONTRADICTING (1)
    [PMID:18579168] No cognitive improvement observed in reaction time
    in non-sleep-deprived adults.

  Weakest link
    The lack of direct evidence for reaction time improvements in
    sleep-deprived adults due to creatine.
```

---

## Assignment requirements → where they are met

| Requirement | Where |
|---|---|
| A prompt qualified by an LLM against the session's rules | [`PROMPT.md`](PROMPT.md) — the qualified v2 prompt |
| The qualification output shown | [`EVALUATION.md`](EVALUATION.md) — a real `gpt-4o` grading run: v1 scored **3/9**, v2 scored **9/9**. Reproduce with `python veritas/evaluate.py`; raw JSON in `veritas/evaluations/` |
| Something built from that prompt | `veritas/` — the prompt is loaded at runtime from `PROMPT.md`; it is not a copy |
| Test output shown | [Run logs](#run-logs) below, plus machine-readable traces in `veritas/runs/*.json` |
| Multiple steps involved | 7 skills, parallel fan-out, and a verifier-driven retry loop — see [architecture](#architecture) |
| Not a summarizer / not a stock or crypto tool | It produces a *verdict with graded citations*, and it actively searches for evidence against the claim |

---

## Architecture

```
              ┌──────────────┐
   claim ────►│  decompose   │  atomic sub-claims + the falsifier
              └──────┬───────┘
                     ▼
              ┌──────────────┐
        ┌────►│    search    │  confirming / DISCONFIRMING / baseline queries
        │     └──────┬───────┘
        │            ▼
        │     ┌──────────────┐
        │     │    fetch     │  ← deterministic code. no LLM. no invented citations.
        │     └──────┬───────┘     PubMed E-utilities + arXiv API
        │            ▼
        │     ┌──────────────┐
        │     │   extract    │  ← parallel fan-out, one call per sub-claim
        │     └──────┬───────┘
        │            ▼
        │     ┌──────────────┐
        │     │    grade     │  design · power · directness · independence
        │     └──────┬───────┘
        │            ▼
        │     ┌──────────────┐
        │     │  synthesize  │  verdict + confidence + contradicting evidence
        │     └──────┬───────┘
        │            ▼
        │     ┌──────────────┐
        └─────┤    verify    │  6 adversarial checks; names the weakest link
  needs_more  └──────┬───────┘  + C0: citation ids checked in code, not judged
  _evidence          │              (overrides an `approved` audit)
   (bounded)         ▼
                  verdict
```

### The seven research skills

| Skill | Job | Why it is its own skill |
|---|---|---|
| `decompose` | Split into atomic P-I-O sub-claims; name the **falsifier** | A claim with no falsifier isn't checkable — catching that early avoids a pointless run |
| `search` | Emit query variants per sub-claim | Forced to emit a **disconfirming** query for every sub-claim; a verifier that only looks for support is a confirmation machine |
| `fetch` | Retrieve from PubMed / arXiv | **Deliberately not an LLM.** The one thing an evidence agent must never do is invent a citation, so this is pure code |
| `extract` | Pull structured evidence per source | Numbers are *copied*, never recalled; `irrelevant` is a first-class direction so search noise isn't padded into the evidence base |
| `grade` | Score each source 0–3 on four axes | Grades the *study*, not whether the conclusion is convenient — a strong contradicting study outranks a weak supporting one |
| `synthesize` | Weigh and rule | `insufficient_evidence` is legitimized so the honest null result is reachable |
| `verify` | Audit the synthesis | Adversarial by design; can **reject and re-route back to `search`**. Its citation check is backstopped by `citations.py`, which is code — an LLM auditing an LLM's citations shares its failure modes |

`fetch` is deterministic; the other six are LLM skills defined by a prompt file
in `veritas/prompts/` plus a `config.yaml` entry. **Adding a skill is a YAML edit
and a prompt file — the orchestrator does not change.**

### What makes it multi-step rather than one big prompt

1. **Sequential dependency** — 7 stages, each consuming the previous stage's typed output.
2. **Parallel fan-out** — `extract` runs concurrently, one call per sub-claim (`ThreadPoolExecutor` in `orchestrator.py`).
3. **A real loop** — `verify` returning `needs_more_evidence` splices back into `search` with the specific gaps it named, bounded by `MAX_ROUNDS` so it always terminates.
4. **Degraded paths** — empty results, all-irrelevant findings, ambiguous claims and out-of-scope claims each have their own branch instead of crashing.

---

## Run logs

Every run writes a full JSON trace to `veritas/runs/` containing each step's
reasoning, output, wall-clock time, and token counts.

### Run 1 — `mixed` verdict, contradicting evidence surfaced

Claim: *"Creatine supplementation improves cognitive performance in sleep-deprived adults"*

```
  [1/7] decompose
        3 sub-claims | falsifier: A well-powered RCT showing no cognitive benefit …

  [2/7] search
        9 queries | stances: baseline, confirming, disconfirming

  [3/7] fetch
    [   confirming] creatine supplementation working memory sleep depriv -> 5 new
    [disconfirming] no effect creatine working memory sleep deprivation  -> 0 new
    [     baseline] creatine cognitive performance sleep deprivation     -> 4 new
    [   confirming] creatine supplementation reaction time sleep depriva -> 2 new
    [disconfirming] no effect creatine reaction time sleep deprivation   -> 1 new
    [     baseline] creatine psychological performance sleep deprivation -> 3 new
    [   confirming] creatine supplementation attention span sleep depriv -> 1 new
    [disconfirming] no effect creatine attention span sleep deprivation  -> 0 new
    [     baseline] creatine effects sleep deprivation cognitive tasks   -> 2 new
        +18 sources (18 total)

  [4/7] extract  (parallel fan-out)
        18 findings | 0 unusable
        directions: {'supports': 7, 'irrelevant': 10, 'contradicts': 1}

  [5/7] grade
        8 graded | weight max 2.0 mean 1.35

  [6/7] synthesize
        verdict: mixed (medium)

  [7/7] verify  (adversarial audit)
        [PASS] C1 citation_integrity
        [PASS] C2 traceability
        [PASS] C3 no_unsupported_inference
        [PASS] C4 contradiction_handling
        [PASS] C5 confidence_calibration
        [PASS] C6 falsifier_addressed
        -> approved
```

**Verdict: MIXED (medium confidence), 18 sources, 41,010 in / 5,741 out tokens.**

Three things worth noting about this run:

- It did **not** simply agree with the claim. It found `PMID:18579168` — a
  reaction-time null result — and downgraded the verdict to `mixed` because of it.
- 10 of 18 findings were marked `irrelevant`. Search engines return noise; the
  agent discarded it rather than padding the evidence base with tangential papers.
- Two of three disconfirming queries returned **zero** new sources. That is an
  honest limitation, not a success: absence of retrievable disconfirming
  literature is not evidence of absence, and `verify` correctly flagged the
  missing reaction-time evidence as the weakest link.

Full trace: `veritas/runs/1784487078-creatine-supplementation-improves-cognitive-perf.json`

### Run 2 — `refuted` verdict, all five finding-directions exercised

Claim: *"Vitamin C supplementation prevents the common cold in the general adult population"* — chosen because the Cochrane literature is broadly negative for the general adult population, so a well-behaved agent should **not** return `supported`.

```
  [4/7] extract  (parallel fan-out)
        21 findings | 4 unusable
        directions: {'null_result': 2, 'irrelevant': 8, 'contradicts': 5,
                     'supports': 5, 'mixed': 1}

  [5/7] grade
        7 graded | weight max 3.0 mean 2.54

  [6/7] synthesize
        verdict: refuted (high)

  [7/7] verify  -> approved, 6/6 checks passed
```

```
  Verdict    REFUTED
  Confidence high
  Sources    16 examined over 1 round(s)

  Vitamin C does not prevent the common cold; it may reduce severity,
  but not incidence.

  RATIONALE
    Most high-weight studies find that Vitamin C does not reduce the
    incidence of the common cold in adults (PMID:15495002,
    PMID:17636648). Supporting evidence for reducing duration and
    severity exists (PMID:10796569, PMID:38082300), but these do not
    compensate for the lack of incidence reduction.

  SUPPORTING (2)
    [PMID:10796569] 8%-9% reduction in duration of cold symptoms.
    [PMID:38082300] 15% decrease in severity.
  CONTRADICTING (2)
    [PMID:9059230]  No reduction in incidence of the common cold.
    [PMID:15495002] No reduction in incidence of the common cold.

  Tokens     50,757 in / 6,492 out
```

This run exercised paths run 1 did not: 4 sources hit the `unusable_sources`
degraded path, and all five `direction` values appeared including `null_result`
and `mixed`. The verdict correctly distinguishes *incidence* (refuted) from
*duration and severity* (supported) rather than collapsing them — which is the
whole point of decomposing into sub-claims.

**A real defect this run exposed — now fixed.** The rationale cites
`PMID:4059230` while the contradicting-evidence list has `PMID:9059230`. One of
those is a corrupted digit, and check `C1 citation_integrity` passed anyway —
the verifier is another LLM call and inherits LLM failure modes.

The fix is deterministic, in `veritas/citations.py`: every `PMID:`/`arXiv:` id
mentioned anywhere in the synthesis is checked for membership in the retrieved
set, the same way `fetch` is code rather than a prompt. Two details matter:

- The bad id lived in the **prose** `verdict_rationale`, not in a structured
  `source_id` field, so the check scans every string in the payload rather than
  walking known keys.
- It **overrides** the audit. A synthesis citing an unretrieved source is not
  approvable whatever the LLM concluded, so `C0` failing forces
  `needs_more_evidence` and spends another round.

This run is the regression fixture: `veritas/tests/` replays its trace and
asserts the checker flags `PMID:4059230` — and that the LLM's `C1` passed it.

Full trace: `veritas/runs/1784487163-vitamin-c-supplementation-prevents-the-common-co.json`

---

## Known limitations

- **Disconfirming queries sometimes return nothing** (2 of 3 in run 1). Absence
  of retrievable disconfirming literature is not evidence of absence, and the
  agent cannot currently distinguish "no contrary evidence exists" from "my
  query was bad."
- **Abstract-only.** Sources are judged on title + abstract; full-text methods
  sections would materially improve `grade`'s design and power scoring.
- **Single-judge rubric score.** The 9/9 in `EVALUATION.md` is one `gpt-4o` call.
  See the caveat in that file.
- **The retry loop has no live run behind it.** Both logged runs were approved
  on round 1. The `needs_more_evidence` splice back into `search` is now
  covered offline — `tests/test_pipeline_gate.py` drives the whole pipeline
  with a stubbed LLM and asserts a bad citation costs a second round — but it
  is still not demonstrated in a committed run against the real APIs.
- **`C0` catches invented ids, not misattributed ones.** Set membership proves
  a cited paper was retrieved; it cannot prove the paper says what the
  synthesis claims it says. That remains an LLM judgement (`C2 traceability`).
  It also compares arXiv ids ignoring the `vN` suffix — the API mints `v2` and
  a citation may drop it, and a false positive there costs a whole retry round.

---

## Running it

```bash
pip install -r requirements.txt

# Anthropic is preferred; OpenAI is supported with the same skill contracts.
export ANTHROPIC_API_KEY=...      # uses claude-opus-4-8
#   or
export OPENAI_API_KEY=...         # uses gpt-4o

cd veritas
python cli.py "your scientific claim here"        # claim mode -> essay + verdict
python cli.py --topic "your open topic here"       # topic mode -> essay, no verdict

# or the UI:
streamlit run app.py
```

No search-API key is needed — PubMed E-utilities and the arXiv API are free and
keyless.

### Configuration

`veritas/config.yaml` holds the skill catalogue, the model IDs, the retry bound
(`max_rounds`), source caps, and which databases are enabled.

---

## Design decisions I'd defend

**`fetch` is code, not an LLM.** Every other skill can be wrong in a recoverable
way. A hallucinated citation is not recoverable — it looks exactly like a real
one. So the one step that produces citations does not go through a model at all.

**Anything that can be asserted in code is not asked of a model.** `fetch`
produces citations, so it is code. Set membership over those citations is
decidable, so `citations.py` is code — and it outranks the LLM auditor rather
than advising it. The model is left the part that genuinely needs judgement.

**Disconfirming search is mandatory, not encouraged.** The prompt requires a
disconfirming query for every sub-claim. Without it, "verification" degenerates
into retrieval of agreement.

**`insufficient_evidence` is a first-class verdict.** Most claim-checkers are
built to produce an answer. The honest null result is what separates verification
from confabulation, so the prompt explicitly tells the model to reach for it.

**`verify` must name a weakest link even when it approves.** An audit that says
"looks good" is not an audit. Forcing it to identify the most vulnerable point
means the output always ships with its own critique attached.

---

## Repository layout

```
Assignment.md            the brief
PROMPT.md                the qualified master prompt  ← the assignment deliverable
EVALUATION.md            rubric grading, v1 (0/9) → v2 (9/9)
README.md                this file
requirements.txt
veritas/
  config.yaml            skill catalogue + pipeline bounds
  prompts/               one contract file per LLM skill
    decompose.md  search.md  extract.md  grade.md  synthesize.md  verify.md
  llm.py                 provider-agnostic client (Anthropic / OpenAI)
  sources.py             PubMed + arXiv clients — the deterministic `fetch` skill
  citations.py           deterministic citation integrity — code, not a prompt
  orchestrator.py        the DAG, the fan-out, the retry loop, the trace writer
  cli.py                 entry point and report formatter
  app.py                 Streamlit UI over both pipelines
  evaluate.py            runs the rubric against v1/v2 — produces EVALUATION.md content
  evaluations/           real judge output: v1.json, v2.json, raw transcripts
  runs/                  JSON traces, one per run
  tests/                 offline tests — no API key, no network
```

Run the tests with:

```bash
cd veritas && python3 -m unittest discover -s tests -v
```
