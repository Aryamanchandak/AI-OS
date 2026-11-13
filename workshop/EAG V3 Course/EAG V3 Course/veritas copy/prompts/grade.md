# SKILL: grade

Score each extracted finding for how much evidentiary weight it should carry.
You are grading the *study*, not whether you like its conclusion. A
well-designed study that contradicts the claim outranks a weak one that
supports it.

Score each dimension 0–3:

**design** — 3: meta-analysis or systematic review of RCTs · 2: RCT or
well-controlled prospective cohort · 1: observational, cross-sectional,
case-control · 0: animal, in-vitro, case report, or unclear

**power** — 3: n ≥ 500 · 2: n 100–499 · 1: n 20–99 · 0: n < 20 or unstated.
(Adjust down one level if the design is within-subject with no control arm.)

**directness** — 3: measures exactly the sub-claim's population, exposure,
and outcome · 2: one of the three is a close proxy · 1: two are proxies ·
0: the link to the sub-claim requires a chain of assumptions

**independence** — 3: replication by an unaffiliated group, or preregistered ·
2: peer-reviewed, no declared conflict · 1: peer-reviewed but industry-funded
or single-group · 0: preprint, or a declared conflict of interest directly
tied to the outcome

Then set `weight` = the arithmetic mean of the four scores, rounded to one
decimal. Do not adjust `weight` by hand to make the synthesis come out a
particular way.

Findings marked `irrelevant` by `extract` are skipped — do not grade them.

## OUTPUT_SCHEMA

```json
{
  "status": "ok | insufficient_input",
  "grades": [
    {
      "source_id": "...",
      "design": 0,
      "power": 0,
      "directness": 0,
      "independence": 0,
      "weight": 0.0,
      "caveat": "the one thing that most limits this study, or null"
    }
  ],
  "strongest_source_id": "the highest-weight source, or null",
  "weakest_source_id": "the lowest-weight source still being counted, or null"
}
```
