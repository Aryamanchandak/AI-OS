# Consequence Radar — Macro View Follow-up

**Status:** Follow-up proposal; not merged into the original  
**Purpose:** Respond to the macro comments in `01-original-plan-with-comments.md` without changing that source document.  
**Relationship to this repository:** This is a proposed interpretation of the product direction, not an agreed specification.

> **Commenting note:** Add comments beneath any `REVIEW` prompt, or edit the decision directly. Unresolved choices are collected again near the end of the document.

> **Scope note:** Sections 1 and 2 contain the revised macro view. Sections 3 onward remain provisional technical exploration and should not be treated as agreed architecture until the macro view is locked.

---

[THE CURRENT VIEW IS SIMPLY NOT GOOD ENOUGH, THE SEARCH ISNT GOOD ENOUGH THE END OUTCOMES ARE TOO VAGUE, THEY DONT TAKE ESTIMATES FROM ANYWHERE FOR EXAMPLE, NOR THEY REACH A FINAL OUTCOME NOT SOMETHING NEEDS TO BE CHANGED IN THE CURRENT SYSTEM BUT SOMETHING TO KEEP AN EYE OUT FOR]  

## 1. Macro product thesis — revised

The proposed product is a research agent for **developing under-examined news into grounded working hypotheses about Indian equities**. [NOT NECESSARILY UNDER EXAMINED NEWS, THERE IS ANOTHER SYSTEM THAT WILL GIVE YOU LIVE NEWS YOU NEED TO COME UP WITH A WAY TO COME UP WITH CLEAR AND WELL EXAMINED OUTPUT TO BE INCLUDED IN A POSSIBLE NEWSLETTER] 

It begins with a finite list of news links supplied to it. It reads enough of each article to understand what has been reported, looks for the item that offers the strongest basis for meaningful second- or third-order reasoning, and asks:

> What might this development set in motion, and how might that eventually matter to an Indian-listed company, an Indian equity sector, or the Indian market more broadly?

The system then builds the answer one causal step at a time. It researches important transitions, records the assumptions required for each transition, looks for reasons the emerging hypothesis may be wrong, and changes the hypothesis when the evidence demands it. [OK YES SOUNDS GOOD, BUT HOW DOES IT DO IT ?]

The final output is a written analysis that says, in substance:

> This development appears worth paying attention to. This is one grounded way it might play out in the Indian equity context. These are the assumptions required for that story to hold, these are the places where it could branch or break, and this is how the working hypothesis changes when those assumptions change.

The product is not claiming to tell the future. It is constructing and testing a plausible causal story. [AND TELLS YOU MORE ABOUT WHAT THE ASSUMPTIONS, ARE, HOW THEY HAVE BEEN BUILT IN TO THE SYSTEM, AND WHAT MIGHT BE THE LIKELIEST OUTCOME OF THIS MAYBE] 

### 1.1 The graph is the agent's working model

The graph is not primarily a visualisation. It is the persistent analytical structure the agent uses to do the work.

It stores:

- What happened or has been proposed.
- The immediate effect being considered.
- The next knock-on effect from that effect.
- The causal mechanism connecting each step.
- The evidence supporting or challenging the connection.
- The assumption required for the connection to hold.
- Alternative branches when an assumption changes.
- Where the chain reaches an Indian stock, sector, or market variable.
- Which parts of the working hypothesis have survived challenge and which have changed.

This gives the agent an external working memory. Instead of repeatedly reconstructing a long argument from prose context, it can inspect and update the current causal model. The graph tells later research calls what needs to be investigated and prevents the final writer from losing the thread. [ I THINK WHATS IMPORTANT HERE IS THAT, YOU USE THE AGENTIC WORK TO MAKE THE GRAPHS , EDIT GRAPHS TEST GRAPHS, WHICH SHOULD ENCODE ALL THE INFORMATION THAT CAN THEN BE FED TO ESSAY WRITING FEATURE, AND THAT ESSAY CAN BE WRITTEN, BASICALLY ALL THE GRAPH AND THE INFORMATION [THE CONTEXT SHOULD BE STROED AND FED] REQUIRED SHOULD BE GIVEN AND WRITTEN]  

The graph should store explicit analytical claims and their support—not private free-form chain-of-thought. Its value comes from preserving a checkable model of the reasoning.[THIS IS WHY WE SHOULD STORE THE CONTEXT AND GIVE THE CONTEXT, WHATS IMPORTANT HERE I GUESS, IS THAT WE GIVE THIS CONTEXT SO FACTS DONT GET MUDDLED UP] 

The graph may be shown in the interface because it is useful for inspection, but visual presentation is secondary to its role in the analysis.

### 1.2 The report is the deliverable

The written analysis is the final shareable output. Once the research graph is stable, one report-writing model call should normally be sufficient because that call is synthesising completed work rather than inventing the analysis from scratch.

Any checks after writing should preferably be deterministic checks—such as verifying that cited source IDs and graph relationships exist—not another open-ended analytical or rewriting loop.

### 1.3 What counts as a promising news item

The system is not trying to identify the objectively “most important news in the world.” It is choosing the best research seed from the list it was given.

A promising seed:

- Contains a concrete reported development, proposal, emerging condition, or credible possibility.
- Supports a plausible immediate effect.
- Provides a grounded base from which non-obvious knock-on effects can be investigated.
- Has a credible route, even if indirect, to an Indian equity consequence.
- Contains assumptions or unresolved transitions worth researching.
- May not yet be fully reflected in the prevailing story around the affected stock or sector.

An idea does **not** need to affect several countries or sectors, produce effects years into the future, or satisfy an arbitrary scale requirement. Those may emerge from the research, but they are not prerequisites. The quality and plausibility of the causal chain matter more than its size or length.

Popularity, emotional intensity, and headline size are not ranking criteria. At most, widespread coverage may be contextual evidence that an idea is already well recognised and therefore less likely to offer an overlooked angle; it should not decide selection by itself.

### 1.4 Rumours, proposals, and possibilities

Rumours, proposals, and forecasts may be valid starting seeds. The system may build a conditional story around them using established facts.

It must preserve the distinction between:

- The rumour or proposal that was actually reported.
- Established facts used to investigate its possible effects.
- The assumptions required to suppose that it proceeds.
- The consequences inferred by the working hypothesis.

The rule is not “only analyse established events.” The rule is “never quietly present the premise or its inferred consequences as established fact.”

### 1.5 How uncertainty should appear

Uncertainty should live inside the working graph as explicit assumptions and forks. The system should show:

- Which transition depends on an assumption.
- Why the assumption currently appears plausible or implausible.
- What alternative follows if it does not hold.
- How changing that assumption alters or breaks the working hypothesis.

The number of resulting branches should be determined by the analysis. The existing analyser's fixed four-scenario structure is not a locked requirement for this new product.

> **REVIEW 1:** Does this now describe the right product: a supplied-news-to-Indian-equity hypothesis builder, with the graph as working memory and the report as the final deliverable?

---



## 2. Macro analytical loop — revised

```text
USER-SUPPLIED NEWS LINKS
                │
                ▼
       INITIAL NEWS READ
 understand the reported development
                │
                ▼
       CHOOSE A RESEARCH SEED
 strongest base for grounded knock-ons
                │
                ▼
      START WORKING GRAPH
 reported seed → immediate effect
                │
                ▼
   DEVELOP THE CAUSAL CHAIN
 one effect → next knock-on effect
                │
        ┌───────┴────────┐
        ▼                ▼
 RESEARCH THIS LINK   RECORD ASSUMPTION
 evidence for/against  and possible fork
        │                │
        └───────┬────────┘
                ▼
      UPDATE WORKING GRAPH
                │
                ▼
 MAP THE PATH INTO INDIAN EQUITIES
 stock / sector / market transmission
                │
                ▼
   TRY TO DISPROVE THE HYPOTHESIS
 attack weak links and hidden assumptions
                │
       ┌────────┴─────────┐
       ▼                  ▼
 REVISE OR BRANCH      RETAIN IF IT HOLDS
       │                  │
       └────────┬─────────┘
                ▼
      STABILISE WORKING GRAPH
                │
                ▼
   ONE-CALL REPORT SYNTHESIS
                │
                ▼
        USER INTERFACE
 primary: shareable written analysis
 secondary: graph, assumptions, evidence
```



### 2.1 How the loop should think

The agent can develop adjacent knock-ons within the same context: immediate effect, effect of that effect, and the next plausible transmission. It should not have to start a separate context for every single edge.

However, periodically it should step back and inspect the whole working graph. That whole-graph check asks:

- Does the complete story remain plausible?
- Have several individually plausible steps combined into an implausible conclusion?
- Is a critical transition unsupported?
- Is the supposed Indian equity consequence too remote or generic?
- Has counterevidence broken an earlier part of the chain?
- Are there two credible branches that should remain separate?

Exactly how many edges may be developed in one context, and when the whole-graph challenge runs, are implementation questions to resolve later.

### 2.2 What “research” means at the macro level

Research is not a generic instruction to collect more articles. It is driven by gaps in the graph.

For a proposed causal transition, the system may look for:

- **Mechanism evidence:** Does A actually have a credible way to cause B?
- **Current conditions:** Are the conditions required for that mechanism present now?
- **Affected actors:** Which company, customer, supplier, regulator, or competitor transmits the effect?
- **Counterevidence:** What could absorb, offset, delay, or reverse it?
- **Comparable cases:** Has a similar mechanism operated before, and what is genuinely comparable?
- **Indian-market connection:** Through what revenue, cost, demand, financing, valuation, regulatory, currency, or competitive channel might the effect reach Indian equities?

Think-tank research, high-quality analytical publications, industry research, primary documents, and credible specialist sources may be especially useful because the purpose is to establish mechanisms, not merely confirm that the headline exists.

### 2.3 De-duplication, not “event clustering” as a product stage

If several supplied links cover the same underlying development, the system should recognise that duplication and treat them as multiple sources for one seed. This is a housekeeping function, not a defining macro stage.

### 2.4 What is not locked yet

The following remain open and should not constrain the macro design:

- Whether the new engine reuses or replaces the existing four-scenario method.
- How many conditional branches the graph should retain.
- How the agent decides that the graph is sufficiently developed.
- How many model calls are used during graph construction and challenge.
- The technical format of graph memory.
- Whether the UI exposes every internal research artifact.
- Whether a later version monitors and updates an existing hypothesis over time.

> **REVIEW 2:** Is this the right top-level loop, especially the sequence of build one causal chain → research its weak links → map it to Indian equities → try to disprove it → write the report?

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