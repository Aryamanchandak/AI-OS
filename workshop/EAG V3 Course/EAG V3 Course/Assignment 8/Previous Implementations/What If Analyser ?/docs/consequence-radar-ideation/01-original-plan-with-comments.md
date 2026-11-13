# Consequence Radar — Product and System Plan

**Status:** Ideation draft for review  
**Purpose:** Define a new, separate system that discovers consequential news developments, converts the strongest candidate into a scenario query, runs a causal analysis, and produces a sourced written report.  
**Relationship to this repository:** This document is stored here for discussion because the proposed system will reuse ideas and selected components from What If Analyser. The new system itself should be built in a separate project so this application remains undisturbed.

> **Commenting note:** Add comments beneath any `REVIEW` prompt, or edit the decision directly. Unresolved choices are collected again near the end of the document.

---



## 1. Product thesis

The proposed product is a **Consequence Radar**: a system that reviews a supplied range of news topics and articles, identifies the development with the greatest plausible downstream impact, turns that development into a precise forward-looking scenario question, analyses its causal consequences, and produces both an inspectable graph [THE GRAPH IS NOT JUST FOR VISUAL PURPOSE IT SO THE AI CAN ACTUALLY TRACE OUT ITS THOUGHTS, BUILD ON IT, CHANGE IT OVER TIME, SO IT DOESNT LOSE THE THREAD IN CONTEXT, AND ISNT LIMITED, ITS A FORM OF TELLING THE AGENT WHAT TO LOOK AT , I THINK, WHAT DO YOU THINK ?] and a written analytical report [WHICH IS ONLY TO SEND, THATS THE FINAL OUTPUT, I DONT IMAGINE ITS MORE THAN ONE LLM CALL].

The system is not intended to:

- Summarise whichever story is receiving the most attention.
- Predict the future with unjustified certainty. [AND NOT ACTUALLY ACT LIKE IT CAN TELL THE FUTURE IT BASICALLY HAS TO SAY SIMPLY, THIS SEEMS BIG THIS IS HOW IT MIGHT PLAY OUT, THE IMPORTANT THING HERE IS THAT IT ATAILORS EVERYTHING TO HOW IT MIGHT PLAY OUT IN THE INDIAN EQUITY MARKET CONTEXT] 
- Treat popularity, emotional intensity, or headline size as equivalent to importance. [ I DONT THINK THIS IS IMPORTANT AT ALL, I DONT THINK ANY OF THIS SHOULD MATTER FOR EXAMPLE, BY THE TIME SOMETHING HAS GOTTEN POPULAR WE HAVE PORBABLY MISSED OUR WINDOW ANYWAY, IN TERMS OF EMOTIONAL INTENSITY I DONT SEE HOW THAT MATTER BUT OPEN TO HEAR WHAT YOU THINK, OR HEADLINE SIZE REALLY DOESNT MATTER BUT AGAIN OPEN TO HEAR WHAT YOU THINK] 
- Turn rumours, proposals, and forecasts into established facts. [DOESNT TURN THEM INTO ESTABLISHED FACTS IT SHOUDL WEAVE A STORY THAT PROPOSES WHAT WILL HAPPEN TO IT, IT BUILDS A STORY AROUND THEM USING ESTABLISHED FACTS] 
- Generate a report whose conclusions cannot be traced back to evidence or the causal model. [WHAT DOES THAT MEAN ? AND IF IT MEANS WHAT I THINK IT MEANS, WHAT IS THE POINT OF THAT, ISNT THAT THE WHOLE POINT OF EVEN BUIILDING THIS THAT IT USES THE GRAPHS TO BUILD ON SOMETHING ? IDEALLY, BECAUSE THATS POINTLESS OTHERWISE, LIKE ITS USELESS WORK OTHERWISE TO DO ALL OF THIS AND NOT EVEN TRACE BACK TO IT]

The central selection question is:

> Which recently reported development [WHAT RECENTLY REPORTED THING] has the [MOST/]greatest credible ability to initiate important second- and third-order consequences that have not yet fully occurred [OR MIGHT NOT HAVE BEEN REALISED, FOR THE STOCK OR THE SECTOR OVERALL FROM THE PERSPECTIVE OF THE EQUITY MARKET]?

### 1.1 Proposed user value

The system should help a user discover:

- News whose significance is not yet obvious. [YOU SHOULD TAKE FROM A LIST OF NEWS GIVEN TO YOU FOR NOW, INSTEAD OF JUST SEARCHING THE WEB ON THIS, ONCE YOU TAKE THE LINKS, YOU THEN GET THE THEME YOU ARE LOOKIGN FOR, TO VERIFY THIS THEME YOU CAN GO AND SEARCH WHEREVER NEWS, AND AN EMPHASIS BECAUSE IT MAYBE IGNORED NOT THAT IT IS MORE IMPORTANT THAN THE REST, THINK TANK RESEARCH AND STUFF LIKE THAT BECAUSE I THINK IT WILL LEND THE MOST TO THIS PROCESS, OR SOMETHIGN LIKE THE ECONOMIST OR SOEMTHIGN, NOT SURE]
- Developments capable of affecting several sectors, countries, institutions, or populations. [THIS SHOULD NOT BE A PRE REQUISITE, YOU WANNA LOOK FOR IDEAS THAT WILL HAVE SECOND ORDER EFFECTS, NOT SIMPLY THE IDEAS THAT REACH ACROSS SECTORS, COUNTRIES, INSTITUTIONS OR POPULATIONS, WE WANT TO HAVE THE BEST SECOND ORDER KNOCK ON EFFECTS OR THIRD ORDER KNOCK ON EFFECTS, WE WANT THE BASE TO BE GOOD FOR NOW, AND HAVE IT AS GROUNDED IN REALITY AS POSSIBLE] 
- Important consequences that may occur months or years after the initial event. [AGAIN NO PRE-REQUISITES BECAUSE WHEN YOU SET THINGS UP LIKE THIS YOU ARE OPENING THE OPPORTUNITY FOR AI TO HALLUCINATE, OR EVEN FUCK UP] 
- The uncertainties that separate materially different futures. [THESE KIND OF UNCERTAINTIES IS WHAT WE WANT OT HIGHLIGHT IN THE GRAPH ESSENTIALLY CLEARLY SEE WHERE THE FORKS ARE AND CLEARLY WE WANT TO SEE WHAT SSUMPTIONS AI MADE ALONG THE WAY, TO SEE IF THEY AGREE OR NOT] 
- The signals that would confirm or disprove the developing causal story. [RATHER HOW ASSUMPTIONS MADE ALONG THE WAY WILL CHANGE THE WORKING HYPOTHESIS] 

> **REVIEW 1:** Is “Consequence Radar” a useful working name, and is this the correct central promise?

---



## 2. End-to-end system

```text
TOPICS, FEEDS, AND ARTICLE LINKS
                │
                ▼
      ARTICLE PRE-READER
  headlines + opening passages
                │
                ▼
         EVENT CLUSTERER
  group coverage of the same event [WHAT DOES THIS MEAN ?] 
                │
                ▼
       CONSEQUENCE SCOUT
 identify plausible downstream paths [BASICALLY I GUESS WE WANT TO LOOK AT, 1) WHAT IS THE IMMEDIATE EFFECT OF THIS, THEN WHATS THE KNOCK ON EFFECT OF THAT, THEN ONCE WE DO THAT WE WANT TO CHECK IS THIS THOUGH PROCESS PLAUSIBLE, NOW REALISTICALLY THIS DOESNT NEED TO ALL HAPPEN OUTSIDE CONTEXT, I FEEL THE OVERALL CHECK HAS TO HAPPEN IN ANOTHER CALL BUT ONE TO NEXT KNOCK ONS CAN HAPPEN IN CONTEXT] [[THINK THIS COMMENT JUMPS THE GUN A BIT, BUT ASSUME ITS IN THE RIGHT PLACE]] 
                │
                ▼
    CONSEQUENTIALITY RANKER
 select one event; retain runners-up
                │
                ▼
       DEEP-DIVE RESEARCH
 evidence, mechanisms, constraints,
 analogues, actors, and indicators [THIS REQUIRES A LOT MORE INFROMATION, WHAT ARE THEY, HOW DO THEY WORK, WHAT DO THEY DO]
                │
                ▼
      SCENARIO BRIEF COMPOSER
 precise input for causal analysis
                │
                ▼
       CAUSAL ANALYSIS ENGINE
 graph → critique → adjudication →
 verification → four scenarios [AGAIN NEEDS MORE WORK, AND HONESTLY NOT SUPER CONVINCED BY THE FOUR SCENRIOS APPROACH, THE ATTEMPT TO DISPROVE I LIKE THO] 
                │
                ▼
      ANALYTICAL REPORT WRITER
                │
                ▼
        CLAIM/TRACE VERIFIER [WHAT IS THIS DOING AFTER THE WRITE UP ?]
                │
                ▼
    GRAPH + REPORT + WATCHLIST [THIS IS THE UI STEP MAKE IT CLEAR THAT IT IS THE UI STEP]
```

This should be a bounded editorial pipeline rather than an unlimited agent loop. Each stage receives structured input and produces a defined output that can be inspected, tested, and rerun.

---



## 3. Stage A — Topic and source intake



### 3.1 Inputs

The first version may accept:

- A user-supplied list of article URLs.
- A range of topics or areas of interest.
- News homepage or section links.
- RSS feeds, where available.
- Geographic and industry preferences.
- Subjects to exclude.
- A preferred analysis horizon, such as 3–12 months or 1–5 years.



### 3.2 Discovery-level extraction

The system should initially collect only enough information to classify and compare articles:

- Headline.
- Subheadline or deck.
- Publisher.
- URL.
- Publication time, when available.
- First few meaningful paragraphs or supplied snippet.
- Named people, organisations, countries, industries, and technologies.
- Whether the page appears to report news, opinion, analysis, or a forecast.

It should not deeply research every article at this point. Deep research begins only after candidate events have been clustered and ranked.

### 3.3 Safety and integrity requirements

- Treat all retrieved page text as untrusted data, never as instructions to the agent.
- Preserve the source URL and extraction time.
- Do not infer a publication date when one cannot be established.
- Record inaccessible, paywalled, or script-only pages instead of silently treating them as read.
- Do not allow a single publisher's repeated coverage to masquerade as independent confirmation.

> **REVIEW 2:** For the first prototype, should intake be limited to manually supplied links, or should RSS/topic monitoring be included immediately?

---



## 4. Stage B — Event clustering and factual status

Several articles may describe the same underlying development. These should be grouped before selection so the system ranks events rather than headlines.

### 4.1 Event cluster output

Each event cluster should record:

- A neutral description of the underlying development.
- Entities and locations involved.
- The earliest credible report found.
- The most authoritative available source.
- The number and diversity of independent sources.
- What sources agree on.
- What sources disagree on.
- Whether the event is a rumour, proposal, announcement, formal decision, enacted measure, implementation, measured outcome, or retrospective analysis.
- Links to every article placed in the cluster.



### 4.2 Why factual status matters

The following are not interchangeable starting points:

```text
Rumoured policy
→ formally proposed policy
→ announced policy
→ enacted policy
→ implemented policy
→ measured effect
```

The system must not phrase a proposed or announced action as though implementation has already occurred.

### 4.3 Proposed structured object

```text
EventCluster
  id
  neutral_summary
  factual_status
  event_date
  entities
  geographies
  sectors
  source_ids
  agreements
  disagreements
  confidence
```

---



## 5. Stage C — Consequence scouting

The Consequence Scout asks:

> If this development continues, is implemented, or triggers a response, what systems could it begin to move?

This is a preliminary breadth pass, not the final causal graph. It exists to determine whether an event is worth deeper analysis.

### 5.1 Pathways to inspect

- Direct operational effects.
- Suppliers and supply chains.
- Customers and substitute products.
- Competitor responses.
- Regulatory imitation or retaliation.
- Financing and insurance consequences.
- Labour and migration effects.
- Infrastructure bottlenecks.
- Behavioural adaptation.
- Political feedback.
- International responses.
- Technology substitution.
- Environmental consequences.
- Delayed effects that may appear only after months or years.



### 5.2 Example

```text
Advanced-equipment export restriction
→ reduced equipment availability
→ manufacturing delays
→ altered capital expenditure
→ slower or relocated capacity growth
→ price changes and strategic substitution
→ political and trade responses
```

The scout should distinguish a plausible path from a supported path. At this stage, paths are hypotheses to investigate rather than conclusions.

---



## 6. Stage D — Consequentiality ranking

The system should not hide selection behind one opaque score. It should grade every candidate across visible dimensions and provide a short evidence-based explanation.

### 6.1 Proposed scoring dimensions


| Dimension              | Selection question                                                             |
| ---------------------- | ------------------------------------------------------------------------------ |
| Scale                  | How many people, firms, sectors, institutions, or countries could be affected? |
| Causal reach           | How many credible downstream pathways might emerge?                            |
| Cross-domain spillover | Could effects travel from one domain into several others?                      |
| Actor response         | Will governments, firms, markets, or populations respond strategically?        |
| Persistence            | Could the effects last or become difficult to reverse?                         |
| Future consequence     | Are important effects still ahead rather than already completed?               |
| Scenario richness      | Are there unresolved branches that create meaningfully different futures?      |
| Under-recognition      | Does its plausible causal importance exceed the attention it is receiving?     |
| Evidence quality       | Is the starting development established well enough to analyse responsibly?    |


Each dimension should use a small ordinal scale, such as `low`, `medium`, or `high`, accompanied by a rationale and supporting source references. Numerical precision such as `83.7% consequential` should be avoided.

### 6.2 Ranking penalties

Candidates should be penalised for:

- Duplicate or syndicated coverage.
- Clickbait without a concrete development.
- Pure commentary or unsupported forecasts.
- Consequences that have substantially finished occurring.
- Dependence on one weak or anonymous source.
- Events too vague to form a causal intervention.
- High emotional importance but little plausible causal branching.
- Downstream claims that remain almost entirely unconstrained speculation.



### 6.3 Selection output

The ranker should return:

- The selected event.
- A concise selection rationale.
- Dimension-by-dimension grades.
- Important weaknesses in the selection.
- The next three or four runners-up.
- A short explanation of why each runner-up was not selected.

The system may proceed automatically, but preserving the runners-up gives the user an audit trail and allows later manual override.

> **REVIEW 3:** Should the system always choose and run one event automatically, or pause for human approval after presenting the ranked shortlist?

---



## 7. Stage E — Deep-dive research

Only the selected event receives wide research. The research plan should cover six evidence families.

### 7.1 Primary confirmation

Find official or first-party material where possible:

- Laws and regulations.
- Government announcements.
- Company filings and statements.
- Court decisions.
- Speeches and transcripts.
- Official datasets.
- Technical or scientific publications.



### 7.2 Causal mechanisms

Find evidence explaining how the initial development could produce its proposed downstream effects.

### 7.3 Affected actors

Identify industries, countries, institutions, communities, supply chains, and decision-makers with meaningful exposure.

### 7.4 Historical analogues

Find previous developments with comparable mechanisms. Analogues should inform possible pathways but must not be treated as proof that history will repeat.

### 7.5 Constraints and counterarguments

Investigate reasons the anticipated effects may be blocked, absorbed, delayed, reversed, or offset.

### 7.6 Leading indicators

Identify observable signals that would show whether a proposed causal pathway is beginning to occur.

### 7.7 Evidence ledger

Research should be converted into atomic claims containing:

```text
EvidenceClaim
  id
  claim
  source_id
  supporting_passage
  claim_type       # fact, forecast, inference, assumption
  stance           # supports, contradicts, context
  geography
  time_horizon
  confidence
  concepts
```

Exact supporting passages should be checked against retrieved source text before a claim is accepted into the ledger.

---



## 8. Stage F — Scenario brief composition

The selected headline should not be passed directly into the causal analyser. Headlines are usually ambiguous about the factual starting point, time horizon, geography, and continuation assumption.

### 8.1 Scenario brief contract

```text
ScenarioBrief
  observed_trigger
  factual_status
  continuation_assumption
  central_question
  geography
  time_horizon
  primary_domains
  affected_actors
  known_constraints
  excluded_assumptions
  seed_source_ids
  evidence_claim_ids
```



### 8.2 Three kinds of truth

Every brief and final report must preserve the distinction between:

```text
OBSERVED
What credible sources establish has happened.

ASSUMED
What the scenario asks us to suppose occurs or continues.

INFERRED
What the causal model suggests may follow.
```



### 8.3 Example conversion

Weak input:

> What happens because of the new semiconductor restrictions?

Preferred scenario brief:

> Following the announced restrictions on advanced semiconductor equipment, what are the most plausible 12–36 month consequences if the rules are implemented substantially as announced, particularly for domestic chip capacity, global equipment suppliers, technology substitution, prices, and geopolitical retaliation?

The trigger may already have happened. The analysis remains prospective because implementation, adaptation, strategic responses, and downstream effects are still unresolved.

> **REVIEW 4:** Should the system generate one tightly scoped brief, or produce two or three alternative analytical framings before choosing one?

---



## 9. Stage G — Causal analysis engine

The current What If Analyser already supplies much of the required middle layer:

- Research planning.
- Source retrieval and ranking.
- Traceable claim extraction.
- Bounded causal-graph construction.
- One skeptical critique.
- One adjudication round.
- Structural sensitivity testing.
- Verification of load-bearing graph relationships.
- Four deterministic scenarios based on two unresolved questions.
- Per-outcome causal traces.
- Short scenario narratives.

The new system should preserve the strongest architectural rules of the existing engine:

- Build the compact graph as a whole instead of recursively expanding nodes.
- Keep propagation deterministic and free of model calls.
- Use a fixed pipeline rather than an unbounded debate or agent loop.
- Use small confidence buckets instead of invented numeric precision.
- Make sources, assumptions, graph changes, and fragile links visible.



### 9.1 Required integration improvement

The current pipeline accepts a plain-language brief and conducts its own research. The new discovery system will already possess a focused evidence pack.

The future integration boundary should therefore accept:

```text
AnalysisRequest
  scenario_brief
  seed_sources
  evidence_claims
  mode
```

This avoids:

- Duplicating research unnecessarily.
- Allowing discovery and analysis to use inconsistent evidence.
- Losing important related articles.
- Weakening traceability between event selection and final conclusions.



### 9.2 Separation from this repository

The new project should interact with the analyser through an adapter. Possible implementation strategies, to decide later, are:

1. Extract the stable engine into a shared installable package.
2. Expose the analyser through a structured API.
3. Vendor a clearly versioned snapshot during early experimentation, then consolidate once the interface stabilises.

The discovery product should not depend directly on this repository's web interface or scrape its rendered HTML.

> **REVIEW 5:** Is the long-term preference a shared Python package, a service/API boundary, or a completely independent copy of the analyser?

---



## 10. Stage H — Written analytical report

The existing three-sentence scenario notes support comparison but are not sufficient for this product. A new report writer should consume the final, verified analysis package.

### 10.1 Proposed report structure

1. **Executive finding**
  What development was selected and why it may be consequential.
2. **What has actually happened**
  The verified trigger, its factual status, and material source disagreements.
3. **Why it may matter more than it appears**
  The non-obvious structural importance and causal reach.
4. **Baseline pathway**
  The central causal chain if no major branch condition changes.
5. **First-, second-, and third-order consequences**
  Effects grouped by causal distance and likely timing.
6. **Four scenario worlds**
  How outcomes differ under the two most important unresolved questions.
7. **Affected actors**
  Exposed groups, possible winners and losers, and likely strategic responses.
8. **Timing**
  Immediate, medium-term, and longer-term effects.
9. **Load-bearing assumptions**
  The causal relationships whose failure would materially alter the outcome.
10. **Falsifiers**
  Evidence that would weaken or disprove the analysis.
11. **Leading indicators and watchlist**
  Specific developments to monitor after the report is produced.
12. **Unknowns and blind spots**
  Important questions the research or model could not resolve.
13. **Sources and confidence**
  Traceable support and a clear distinction between fact, forecast, assumption, and inference.



### 10.2 Writing constraints

- Use conditional language rather than presenting scenarios as forecasts.
- Do not attach probabilities unless a defensible external method supplies them.
- Do not introduce a causal conclusion absent from the final graph.
- Clearly label any synthesis that goes beyond a directly sourced claim.
- Link substantive claims to evidence claims or graph paths.
- Describe disagreement and missing evidence rather than smoothing them away.
- Prefer precise time horizons and actors over generic language.

> **REVIEW 6:** What should the default report length and audience be: a concise executive brief, a detailed analyst memo, or both?

---



## 11. Stage I — Report verification

A separate verification pass should compare the written report with the structured analysis package.

### 11.1 Checks

- Does every material factual statement have a valid source?
- Does each causal conclusion correspond to a graph path?
- Are observed facts, scenario assumptions, and model inferences labelled correctly?
- Did the report invent an actor, number, date, mechanism, or probability?
- Did it omit a major contradictory claim?
- Did it overstate an edge marked mixed, contradicted, assumed, or unverified?
- Does every stated falsifier genuinely challenge the analysis?
- Do the leading indicators correspond to load-bearing mechanisms?



### 11.2 Verification output

```text
ReportAudit
  supported_statements
  unsupported_statements
  overstated_statements
  missing_counterevidence
  incorrect_fact_assumption_inference_labels
  required_revisions
  unresolved_warnings
```

The verifier may request one bounded revision. It should not begin an open-ended writer–critic loop.

---



## 12. Final product output

A completed run should show:

1. The selected development and selection rationale.
2. The ranked runners-up.
3. The generated scenario brief.
4. The four-scenario outcome matrix.
5. The final causal graph.
6. The analytical report.
7. The evidence ledger and sources.
8. Critique, adjudication, and graph changes.
9. Load-bearing assumptions and falsifiers.
10. A monitoring watchlist of leading indicators.
11. Visible limitations, research failures, and unresolved disagreements.

The graph and report should be complementary:

- The graph provides inspectability and structural reasoning.
- The report provides interpretation, timing, context, and readability.
- The evidence ledger constrains both.

---



## 13. Proposed MVP

The first version should prove the core editorial proposition without requiring continuous monitoring or production infrastructure.

### 13.1 MVP scope

1. Accept 20–50 manually supplied article links and a topic range.
2. Extract headlines and opening passages.
3. Cluster articles into distinct developments.
4. Rank the five most consequential developments.
5. Automatically select one while retaining the shortlist and explanations.
6. Conduct deeper research on the selected development.
7. Generate one structured scenario brief.
8. Run the causal analyser.
9. Produce a sourced analytical memo of approximately 1,000–1,500 words.
10. Verify the memo against the graph and evidence.
11. Display the graph, scenario matrix, report, assumptions, falsifiers, and watchlist.



### 13.2 Explicitly out of scope for the MVP

- Continuous autonomous crawling.
- User accounts and collaboration.
- Scheduled newsletters or alerts.
- A permanent knowledge graph.
- Portfolio-specific recommendations.
- Automatic trading or operational decisions.
- Precise outcome probabilities.
- Unlimited agent debate.
- Publishing without an audit trail.



### 13.3 MVP success criteria

The prototype succeeds if it can repeatedly demonstrate that:

- It clusters duplicate reporting correctly.
- Its selected event is defensibly more consequential than its runners-up.
- The scenario brief is factual, prospective, and sufficiently precise.
- The graph exposes meaningful causal branches rather than restating the article.
- The report adds useful interpretation without departing from the graph and evidence.
- A reviewer can see why the system selected the story and what would prove its analysis wrong.

---



## 14. Suggested implementation phases



### Phase 0 — Evaluation set

Before building the full application, assemble several historical news batches and manually label:

- Which articles belong to the same event.
- Which events appeared most consequential at the time.
- What downstream pathways were knowable at the time.
- Which later consequences should not have been knowable without hindsight.

This becomes the test set for selection quality and hindsight leakage.

### Phase 1 — Discovery prototype

Build article extraction, event clustering, consequence scouting, ranking, and shortlist presentation. Do not integrate the full causal engine yet.

### Phase 2 — Research and brief composition

Add focused research, the evidence ledger, factual-status handling, and structured scenario briefs.

### Phase 3 — Analyser adapter

Connect the scenario brief and evidence pack to a versioned causal-analysis interface. Preserve deterministic propagation and existing graph validation.

### Phase 4 — Report and verifier

Generate the full report, add claim-to-source and statement-to-graph traceability, and allow one bounded correction pass.

### Phase 5 — Product interface and persistence

Add run history, shortlist comparison, source inspection, report export, and watchlist updates.

### Phase 6 — Monitoring

Only after selection quality is established, add scheduled feed ingestion, event updates, alerts, and report refreshes.

---



## 15. Major risks and design responses


| Risk                                                            | Proposed response                                                                    |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| The agent selects sensational rather than consequential stories | Use multidimensional scoring, penalties, runners-up, and evidence-backed rationales. |
| Several articles create false confidence through repetition     | Cluster syndicated coverage and measure publisher/source independence.               |
| A proposal is treated as an accomplished fact                   | Preserve factual status from intake through the final report.                        |
| The system invents distant knock-on effects                     | Treat scout pathways as hypotheses and require mechanism research before graph use.  |
| The report becomes more confident than the graph                | Verify every substantive conclusion against graph paths and edge evidence.           |
| The system overlooks counterevidence                            | Require skeptical search families and show unresolved contradictions.                |
| The same research is performed twice                            | Pass the discovery evidence pack through a defined analyser interface.               |
| Retrieved articles contain prompt injection                     | Treat page content as quoted data inside strict structured tasks.                    |
| Historical evaluation introduces hindsight                      | Freeze evidence to material available by the simulated run date.                     |
| Autonomous operation hides bad choices                          | Retain shortlist scores, explanations, inputs, and intermediate artifacts.           |
| Reports imply probabilities the engine does not calculate       | Use conditional scenarios and ordinal confidence only.                               |
| Costs grow across many candidate stories                        | Use shallow extraction for all candidates and deep research only for the winner.     |


---



## 16. Decisions still required

1. **Working name:** Consequence Radar or another name?
2. **Initial sources:** Supplied links only, or supplied links plus RSS/topic search?
3. **Selection autonomy:** Fully automatic, human approval, or an optional approval mode?
4. **Number of analyses:** Only the top event, or the top two or three?
5. **Brief composition:** One brief or several alternative framings?
6. **Time horizon:** User-selected, agent-selected, or both?
7. **Primary audience:** General reader, executive, policy analyst, investor, or domain researcher?
8. **Report format:** Executive brief, detailed memo, or both?
9. **Analyser boundary:** Shared package, API/service, or versioned copy?
10. **Evidence threshold:** What minimum source quality is required before an event can be analysed?
11. **Human review:** Is review optional, required before publishing, or absent in the autonomous version?
12. **Monitoring:** Should the final watchlist later trigger updates to an existing analysis?

---



## 17. Recommended first design decision

Before choosing models, frameworks, storage, or UI technology, define and test the **consequentiality rubric**.

That rubric is the distinctive intellectual component of the product. Article extraction, web research, graph building, and report generation can all be implemented in several reasonable ways. The harder question is whether the system can reliably distinguish:

> “This is receiving attention”

from:

> “This could reorganise several systems, and its most important consequences are still ahead.”

The first practical exercise should therefore be to collect 10–20 mixed news batches and manually rank the events. Those examples will reveal whether the proposed dimensions are sufficient and will provide the evaluation material needed before autonomous selection is trusted.
