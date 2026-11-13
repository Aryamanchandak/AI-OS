# `models/__init__.py` — explained

This module is the shared vocabulary of the whole pipeline. It defines every Pydantic schema that flows between stages — raw news input, the causal graph and its nodes/edges/assumptions/estimates, evidence and sources, challenge/adjudication results, the final report, and a handful of "batch wrapper" schemas used purely to bound and validate LLM structured output. It has no logic of its own beyond validation; every other package in `src/consequence_radar/` imports its types rather than defining its own.

## Module-level helpers

`NonEmpty` (line 10) is a type alias — `Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]` — used throughout the file wherever a string field must not be blank. It is applied inconsistently: many "core" domain models (`CausalNode.label`, `CausalNode.description`, `Assumption.statement`, `Estimate.metric`, `Estimate.caveat`, `NewsletterReport` fields, etc.) use it, but several closely related models use plain `str` instead — `RejectedClaim` (all four fields), `EvidenceClaimDraft.claim`/`exact_passage`, `SourceRecord.url`/`title`/`extracted_text`, `DiscoveryExtract.canonical_url`. This looks intentional for the "draft" evidence models (raw LLM output before verification shouldn't be over-constrained) but the inconsistency on `SourceRecord` and `RejectedClaim` looks more like an oversight than a deliberate design choice.

`MAX_GENERATED_ITEMS` (lines 19–28) is a dict of integer ceilings keyed by a semantic name (`"candidates"`, `"tasks"`, `"claims"`, `"findings"`, `"operations"`, `"cases"`, `"ids"`, `"notes"`). The comment directly above it explains the rationale clearly: these caps exist so that a runaway LLM generation gets truncated locally by the caller rather than blowing past `max_output_tokens` and producing invalid JSON that fails Pydantic validation outright. The comment notes the ceilings are set deliberately high — "several callers (`rank_candidates`, `generate_tasks`) deliberately let the model overshoot and slice locally" — and cites a real incident where a runaway response emitted "roughly ninety candidate seeds" as the reason the `candidates` cap is set well above what's plausible (25). Note `"findings"` (100) is reused for two different purposes: `ChallengeResult.findings` and `AdjudicationResult.decisions` both use `MAX_GENERATED_ITEMS["findings"]` even though decisions and findings are conceptually different lists — there's no dedicated `"decisions"` key.

`utcnow()` (lines 31–32) is a trivial wrapper around `datetime.now(timezone.utc)`, used as a `default_factory` for timestamp fields (`SourceRecord.retrieved_at`, `GraphRevision.timestamp`, `ModelCallRecord.created_at`). Its only purpose is to give those `default_factory=` call sites a named, timezone-aware function instead of a bare lambda.

`StrictModel` (lines 35–36) is the base class every model in the file inherits from. It sets `model_config = ConfigDict(extra="forbid", validate_assignment=True)`. `extra="forbid"` means any unexpected key in input data raises a validation error rather than being silently dropped — this matters a lot given that most of these models are populated from LLM JSON output, where a hallucinated or misspelled field should fail loudly. `validate_assignment=True` means mutating an already-constructed instance (`obj.field = x`) re-runs validation, not just at construction time.

## Enums

`FactualStatus` (lines 39–48) is a `StrEnum` with nine values ranging from `RUMOUR` through `MEASURED_OUTCOME`, plus `ANALYSIS_OR_FORECAST` and `UNCLEAR`. It represents how far a piece of news has progressed from speculation to confirmed outcome, and is used both on `DedupGroup` and `CandidateSeed`/`ReportContext` to track the "how real is this yet" dimension of a story.

`RunStatus` (lines 51–65) is a `StrEnum` with fourteen values describing pipeline run state — `QUEUED` through `PRE_READING`, `SELECTING`, `BUILDING_GRAPH`, `RESEARCHING`, `QUANTIFYING`, `CHALLENGING`, `ADJUDICATING`, `COMPILING_CONTEXT`, `WRITING_REPORT`, then terminal states `COMPLETED`, `COMPLETED_WITH_WARNINGS`, `FAILED`, `REPORT_VALIDATION_FAILED`. This enum's ordering doubles as an implicit description of the pipeline's stage sequence — reading it top to bottom is effectively a one-line map of the whole system.

## Ingestion models

`NewsItem` (68–75) is a single input news item: `id`, `url` (typed as `HttpUrl` — the one place in the file a URL field gets real URL validation rather than being a plain string), `headline`, `snippet`, `publisher`, `published_at`, `topic`, all optional except `url`.

`NewsBatch` (78–83) wraps a list of `NewsItem` with `Field(min_length=1, max_length=100)` — a batch cannot be empty or exceed 100 items. `target_market` is a `Literal["indian_equities"]` fixed to that one value (there is no other market currently possible, which is consistent with the project being India-equities focused per the architecture docs), `report_audience` defaults to `"informed Indian equity-market reader"`.

`DiscoveryExtract` (86–96) represents the result of fetching a `NewsItem`'s underlying page: `item_id`, `canonical_url` (plain `str`, not `HttpUrl`), optional `headline`/`subheadline`/`publisher`/`published_at`, `text` (default `""`), `fetched: bool = False`, and `failure_reason: str | None`. The `fetched`/`failure_reason` pair is how a failed fetch is represented — there's no exception type, just these two fields, meaning callers must remember to check `fetched` before trusting `text`.

`DedupGroup` (98–106) groups near-duplicate `NewsItem`s: `id`, `member_item_ids`, `authoritative_item_id` (which member is treated as canonical), `publisher_diversity`, `agreement`, `disagreement` (all default to empty lists), and `factual_status` defaulting to `FactualStatus.UNCLEAR`.

## Candidate selection

`Grade` (108) is `Literal["low", "medium", "high"]`, reused across many models (`CandidateSeed.grades` values, `CausalEdge.confidence`, `Assumption` isn't graded this way but `ResearchTask.priority` and `ChallengeFinding.severity` both are).

`SELECTION_DIMENSIONS` (109–113) is a fixed set of seven strings: `grounded_starting_point`, `immediate_effect_plausibility`, `knock_on_potential`, `indian_equity_transmission`, `researchability`, `decision_relevance`, `unresolved_assumptions`. This is the rubric used to grade candidate story premises.

`CandidateSeed` (116–133) represents one candidate story premise before it's turned into a graph: `id`, `source_item_ids`, `reported_premise`, `factual_status`, `possible_immediate_effect`, `possible_indian_equity_route` (all `NonEmpty`), `grades: dict[str, Grade]`, `rationale`, `weaknesses` (default empty list), `selected: bool = False`. The `all_dimensions` field validator (128–133) enforces that `grades` contains *exactly* the keys in `SELECTION_DIMENSIONS` — not a subset, not a superset — via `set(value) != SELECTION_DIMENSIONS`. A grades dict missing one dimension, or with an extra one, is rejected with a `ValueError` naming the required set.

## The causal graph

`CausalNode` (136–144): `id`, `label` and `description` (`NonEmpty`), `node_type` restricted to a `Literal` of six values (`news_seed`, `driver`, `intermediate`, `company_metric`, `sector_metric`, `market_outcome`), optional `geography`/`time_horizon`, `entity_ids` (default empty list), and `status: Literal["active", "rejected", "superseded"] = "active"`. The presence of a `status` field rather than deletion implies the graph is designed to be append-only/soft-delete — nodes get marked `rejected` or `superseded` instead of being removed from the `nodes` list. This is confirmed by how the `graph` package's `apply_patch` (see below) handles `reject_node` by rewriting the node's status field rather than filtering it out of the list.

`CausalEdge` (147–161): `id`, `src`, `dst`, `mechanism` (`NonEmpty`), `direction: Literal["positive","negative","mixed","unknown"]`, `strength: Literal["low","medium","high","unknown"]`, `confidence: Grade`, optional `time_lag`/`condition_text`, four lists of cross-referencing IDs (`assumption_ids`, `supporting_claim_ids`, `contradicting_claim_ids`, `estimate_ids`, all default empty), and `status: Literal["proposed","supported","mixed","contradicted","assumption_only","rejected"]` — this one has no default, so every edge must explicitly state its status. Note there's no `src`/`dst` referential-integrity check here — nothing in this class verifies `src`/`dst` point at real node IDs; that must be enforced elsewhere (likely in `graph/__init__.py`'s `validate_graph`), since `models/__init__.py` doesn't import or reference the sibling `nodes` list from within `CausalEdge`.

`Assumption` (164–174): `id`, `statement` and `basis` (`NonEmpty`), `required_for_edge_ids` (required, no default — unlike most other cross-ref lists in the file), `likelihood: Literal["unlikely","possible","likely","unknown"]`, `likelihood_basis: Literal["sourced","inferred","unknown"]`, `supporting_claim_ids`/`contradicting_claim_ids` (default empty), `if_false_effect` (`NonEmpty`), `material: bool` (required, no default — every assumption must be explicitly flagged as material or not).

`Estimate` (177–207) is the most heavily validated model in the file and worth reading closely. Fields: `id`, `metric` (`NonEmpty`), `estimate_type: Literal["source_value","source_range","derived_range","directional_only","unknown"]`, `low`/`central`/`high` as `Decimal | None` (using `Decimal` rather than `float` — deliberate, to avoid floating-point precision artifacts in numeric estimates that flow into a financial report), `unit`/`period`/`currency` optional strings, `formula` optional string, `input_estimate_ids`/`source_claim_ids`/`assumptions` (default empty lists), `caveat` (`NonEmpty`, required).

Two validators layer on top:
- `ordered_range` (193–199), a `field_validator` on `high`, checks `high >= low` when both are present, using `info.data.get("low")` to read the already-validated `low` value (this works because Pydantic v2 validates fields in declaration order and `low` is declared before `high`).
- `lineage_rules` (201–207), a `model_validator(mode="after")`, enforces two invariants: if `estimate_type` is `source_value` or `source_range`, `source_claim_ids` must be non-empty ("sourced estimates require at least one source claim"); if `estimate_type` is `derived_range`, both `formula` and `input_estimate_ids` must be present.

What's notably *not* enforced: there is no check that `directional_only` or `unknown` estimates have `low`/`central`/`high` all `None`. A caller could construct `Estimate(estimate_type="directional_only", low=Decimal("5"), central=Decimal("10"), high=Decimal("20"), ...)` and it would pass validation cleanly even though a "directional only" estimate conceptually shouldn't carry numeric values. This is exactly the kind of unenforced invariant worth knowing about if code downstream assumes `directional_only` estimates never have numbers.

## Evidence and sources

`SourceRecord` (210–221): `id`, `url` and `title`/`publisher` as plain `str` (not `HttpUrl` despite `url` being, well, a URL), `retrieved_at` defaulting to `utcnow()`, `extracted_text`, `content_type` defaulting to `"text/html"`, optional `published_at`, `source_type` defaulting to `"web"`, `suitability_reason` defaulting to `""`, `fetch_failure` optional. Like `DiscoveryExtract`, failure is represented by an optional string field rather than a distinct type.

`EvidenceClaim` (224–234): `id`, `source_id`, `claim` and `exact_passage` (`NonEmpty`), `claim_type: Literal["fact","estimate","forecast","inference","assumption"]`, `stance: Literal["supports","contradicts","context"]`, `concepts: list[str]` (required, no default), optional `geography`/`time_horizon`, `passage_verified: bool` (required, no default). This is the "accepted" claim shape used once a claim has been checked.

`RejectedClaim` (237–242) is a much looser sibling: `claim`, `source_id`, `exact_passage`, `reason`, all plain `str` with no `NonEmpty` constraint and no enums — presumably because a rejected claim is being recorded for audit purposes, not re-validated as a first-class object.

`EvidenceClaimDraft`/`EvidenceClaimDrafts` (375–387) are the pre-verification counterpart to `EvidenceClaim`: same shape minus `passage_verified` and `id`, and using plain `str` instead of `NonEmpty` for `claim`/`exact_passage`. `EvidenceClaimDrafts` just wraps `claims: list[EvidenceClaimDraft]` bounded by `MAX_GENERATED_ITEMS["claims"]` (250) — this is one of the "LLM output wrapper" models described below.

## Graph mutation and revision

`CausalGraph` (244–250) is the container: `version: int = Field(ge=1)`, `nodes: list[CausalNode]`, `edges: list[CausalEdge]`, `assumptions`/`estimates` (default empty), `feedback_warnings: list[str]` (default empty) — a place to accumulate non-fatal warnings surfaced during graph construction/repair.

`GraphOperation` (253–256) is a single mutation instruction: `op` restricted to a `Literal` of ten values (`add_node`, `update_node`, `reject_node`, `add_edge`, `update_edge`, `reject_edge`, `add_assumption`, `update_assumption`, `add_estimate`, `update_estimate`), `target_id`, and `value: dict[str, Any] | None`. Notice there is no `reject_assumption` or `reject_estimate` op in the literal — nodes and edges can be soft-rejected but assumptions and estimates apparently cannot be, at least not through this operation vocabulary.

`GraphPatch` (259–263) bundles a bounded list of `GraphOperation`s (`max_length=MAX_GENERATED_ITEMS["operations"]`, 200), a `reason` (`NonEmpty`), `evidence_ids` bounded to `MAX_GENERATED_ITEMS["ids"]` (250), and `remaining_gaps` bounded to `MAX_GENERATED_ITEMS["notes"]` (60).

`GraphRevision` (266–277) is an audit-trail record of one patch application: `id`, `run_id`, optional `model_call_id`, `reason`, `evidence_ids` (default empty), `timestamp` defaulting to `utcnow()`, `before_version`/`after_version` (plain ints, no field cross-check that `after_version == before_version + 1` — that relationship is asserted nowhere in this file), `operations: list[GraphOperation]`, `validation_errors` (default empty — meaning a `GraphRevision` can represent a patch attempt that partially or fully failed validation, with the errors recorded here rather than the whole revision being discarded).

## Research, challenge, adjudication, cases

`ResearchTask` (279–288): `id`, `target_type: Literal["edge","assumption","estimate","entity","whole_graph"]`, `target_id`, `question` (`NonEmpty`), `intent` restricted to a `Literal` of seven research intents (`confirm_premise`, `test_mechanism`, `find_current_conditions`, `quantify`, `find_indian_exposure`, `find_counterevidence`, `find_comparable_case`), `preferred_source_types`/`search_queries` (required lists, no default), `priority: Grade`, `status: Literal["pending","complete","failed","not_found"] = "pending"`.

`ChallengeFinding` (291–299): `id`, `target_type: Literal["node","edge","assumption","estimate"]`, `target_id`, `failure_mode`/`explanation` as plain `str` (not `NonEmpty` — inconsistent with most other "explanation-like" fields in the file), `severity: Grade`, `claim_ids` (default empty).

`AdjudicationDecision` (301–305): `finding_id`, `decision: Literal["accept_and_revise","accept_and_remove","accept_and_branch","reject_with_reason","unresolved"]`, `reason` (plain `str`), `operations: list[GraphOperation]` (default empty) — this is how an adjudication decision translates into an actual graph mutation when the decision is `accept_and_revise`/`accept_and_branch`.

`Case` (308–322) represents one causal path through the graph, from seed to market outcome: `id`, `name`, `path_node_ids`/`path_edge_ids`/`required_assumption_ids`/`supporting_claim_ids`/`contradicting_claim_ids`/`estimate_ids` (all required lists), `equity_implication_direction: Literal["positive","negative","mixed","unknown"]`, `quantification_status: Literal["quantified","directional_only"]`, `time_horizon` (plain `str`, required), `weakening_observation` (plain `str`, required — every case must state what would weaken it, even if that value ends up being an empty-ish placeholder string since there's no `NonEmpty` constraint here), `central: bool = False`, `broken_reason: str | None = None` (populated when a case represents a path that was found to be broken rather than viable — used by `CaseSelection.broken_paths` below).

## Report assembly and output

`ReportContext` (325–340) is the large bundle handed to the report-writing stage: selected premise/factual status/equity focus, the full `graph`, `central_case: Case`, `material_alternatives: list[Case]`, `assumptions`, `accepted_claims`/`contradicting_claims` (both `list[EvidenceClaim]`), `estimates`, `challenge_findings`, `adjudication_decisions`, `known_gaps`/`research_failures` (lists of plain strings), `sources: list[SourceRecord]`. This is essentially "everything the report generator needs in one object," and every field is required with no defaults.

`NewsletterReport` (343–351) is the final output shape: `headline`, `dek`, `why_this_matters`, `article_markdown`, `central_case_summary` (all `NonEmpty`), `key_assumptions`/`what_changes_the_view` bounded to `MAX_GENERATED_ITEMS["notes"]` (60), `source_ids_used` bounded to `MAX_GENERATED_ITEMS["ids"]` (250).

`ModelCallRecord` (354–364) is telemetry for a single LLM call: `id`, `run_id`, `stage`, `model_name`, `prompt_version`, `input_tokens`/`output_tokens` default `0`, `retry_count` default `0`, `error: str | None`, `created_at` defaulting to `utcnow()`. Nothing in the file computes cost from tokens — this is a raw record only.

## LLM-output wrapper models

The last block of the file (367–402) is a set of thin "envelope" models whose sole purpose is to give an LLM structured-output call something to return that (a) has a bounded list length via `MAX_GENERATED_ITEMS`, protecting against runaway generation as described in the module comment, and (b) can be validated as a single object: `CandidateSelection` (candidates, max 25), `ResearchTaskList` (tasks, max 60), `EvidenceClaimDrafts` (claims, max 250), `ChallengeResult` (findings, max 100), `AdjudicationResult` (decisions, max 100 — reusing the `"findings"` cap rather than a dedicated key), and `CaseSelection` (`central_case: Case` required plus `material_alternatives`/`broken_paths`, each capped at 25 via `MAX_GENERATED_ITEMS["cases"]`).

## Non-obvious things worth flagging

- The `directional_only`/`unknown` gap in `Estimate.lineage_rules` noted above: numeric fields are never forbidden for non-numeric estimate types.
- `NonEmpty` vs plain `str` is applied inconsistently across otherwise-parallel fields (`EvidenceClaim` vs `RejectedClaim`/`EvidenceClaimDraft`; `ChallengeFinding.explanation` vs most other explanatory fields).
- `HttpUrl` is used only for `NewsItem.url`; every other URL-shaped field (`DiscoveryExtract.canonical_url`, `SourceRecord.url`) is a plain `str`.
- `GraphOperation.op`'s literal has no reject variant for assumptions or estimates, only for nodes and edges.
- `GraphRevision.before_version`/`after_version` have no cross-field validator tying them together, unlike `Estimate.low`/`high`.
- `MAX_GENERATED_ITEMS["findings"]` is reused for `AdjudicationResult.decisions`, a different concept than `ChallengeResult.findings`.

## How this connects to the rest of the codebase

A repo-wide grep for imports of `consequence_radar.models` (or the relative `..models`/`.models` forms) shows essentially every package in `src/consequence_radar/` depends on this module:

- `ingest/__init__.py` imports `DiscoveryExtract, NewsBatch, NewsItem` — the raw ingestion stage.
- `deduplicate/__init__.py` imports `DedupGroup, DiscoveryExtract, FactualStatus`.
- `select/__init__.py` imports `CandidateSeed, CandidateSelection, DedupGroup, DiscoveryExtract` — candidate ranking/selection.
- `graph/__init__.py` imports `CausalEdge, CausalGraph, CausalNode, GraphOperation, GraphPatch, GraphRevision` at module level, and additionally does local, function-scoped imports `from .models import Assumption` / `from .models import Estimate` inside `apply_patch()` (around lines 100–109) to handle the `add_assumption`/`update_assumption`/`add_estimate`/`update_estimate` operations. That `.models` import path resolves to `consequence_radar.graph.models`, which does not exist as a file in the `graph/` package (only `..models`, i.e. `consequence_radar.models`, exists) — this looks like a bug that would raise `ModuleNotFoundError` the first time any of those four operation types is actually applied via `apply_patch`.
- `research/__init__.py` imports `CausalGraph, EvidenceClaimDrafts, ResearchTask, ResearchTaskList, SourceRecord`.
- `evidence/__init__.py` imports `EvidenceClaim, EvidenceClaimDraft, RejectedClaim, SourceRecord`.
- `quantify/__init__.py` imports `Estimate`.
- `challenge/__init__.py` imports `AdjudicationResult, ChallengeResult, CausalGraph, EvidenceClaim, GraphPatch`.
- `cases/__init__.py` imports `CaseSelection, CausalGraph, EvidenceClaim`.
- `report_context/__init__.py` imports `AdjudicationDecision, CandidateSeed, CaseSelection, ChallengeFinding, CausalGraph, EvidenceClaim, ReportContext, SourceRecord`.
- `report/__init__.py` imports `NewsletterReport, ReportContext`.
- `pipeline/__init__.py` imports `GraphRevision, NewsBatch, RunStatus` — orchestration/state tracking.
- `storage/__init__.py` imports `NewsBatch, RunStatus`.
- `web/app.py` imports `NewsBatch` at module level and `NewsletterReport` inline (line 140) inside a function.

Every package's own test file (`test_ingest.py`, `test_evidence.py`, `test_quantify.py`, `test_graph.py`, `test_cases.py`, `test_report_context.py`, `test_report.py`, `test_deduplicate.py`, and `providers/model/test_model.py`) also imports directly from `consequence_radar.models` to construct fixtures, confirming this module is the common vocabulary every other test suite builds on too.
