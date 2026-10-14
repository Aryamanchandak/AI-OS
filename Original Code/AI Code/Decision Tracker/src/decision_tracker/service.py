from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import (
    ClaimType,
    Decision,
    DecisionClass,
    DecisionDraft,
    DecisionStatus,
    Integrity,
    Process,
    Resolution,
    ResolutionInput,
    SourceClassification,
)
from .scoring import score_binary
from .store import SQLiteEventStore, canonical_json, hash_parts


class DecisionTrackerError(ValueError):
    pass


class DecisionTracker:
    def __init__(self, db_path: str | Path = ".decision-tracker/decision_tracker.db") -> None:
        self.store = SQLiteEventStore(db_path)
        self.store.initialize()

    @staticmethod
    def now() -> datetime:
        return datetime.now().astimezone()

    def log(self, draft: DecisionDraft) -> Decision:
        if draft.source_classification == SourceClassification.BLOCKED:
            raise DecisionTrackerError(
                "blocked source classification cannot be persisted; no record was created"
            )

        created_at = self.now()
        with self.store.connect() as connection:
            with connection:
                decision_id = self.store.next_id(created_at.year, connection)
                horizon = None
                if draft.claim.resolution_date:
                    horizon = max(0, (draft.claim.resolution_date - created_at.date()).days)
                decision = Decision(
                    id=decision_id,
                    created_at=created_at,
                    **draft.model_dump(by_alias=True),
                    horizon_days=horizon,
                    status=DecisionStatus.DRAFT,
                    process=self._process(draft),
                )
                self.store.append(connection, decision, "DRAFT_CREATED", created_at)
        return decision

    def commit(self, decision_id: str) -> Decision:
        decision = self.require(decision_id)
        if decision.status != DecisionStatus.DRAFT:
            raise DecisionTrackerError("only DRAFT decisions can be committed")
        failures = self._gate_failures(decision)
        if failures:
            raise DecisionTrackerError("admission gate failed: " + "; ".join(failures))

        committed_at = self.now()
        with self.store.connect() as connection:
            with connection:
                head = connection.execute(
                    "SELECT head_hash FROM commit_chain WHERE singleton = 1"
                ).fetchone()[0]
                committed = decision.model_copy(
                    update={"status": DecisionStatus.COMMITTED, "integrity": Integrity()}
                )
                snapshot = committed.model_dump(mode="json", by_alias=True)
                commit_hash = hash_parts(head, canonical_json(snapshot))
                committed = committed.model_copy(
                    update={"integrity": Integrity(commit_hash=commit_hash, prev_hash=head)}
                )
                self.store.append(connection, committed, "COMMITTED", committed_at)
                connection.execute(
                    "UPDATE commit_chain SET head_hash = ? WHERE singleton = 1", (commit_hash,)
                )
                live = committed.model_copy(update={"status": DecisionStatus.LIVE})
                self.store.append(connection, live, "ACTIVATED", committed_at)
        return live

    def resolve(self, decision_id: str, resolution_input: ResolutionInput) -> Decision:
        decision = self.require(decision_id)
        if decision.status != DecisionStatus.LIVE:
            raise DecisionTrackerError("only LIVE decisions can be resolved")
        if decision.decision_class == DecisionClass.FORECAST and (not resolution_input.resolver_source or not resolution_input.automated):
            raise DecisionTrackerError("FORECAST resolution requires an automated resolver and source provenance")

        score = {"brier": None, "log_score": None, "skill_vs_base_rate": None}
        if decision.decision_class == DecisionClass.FORECAST and decision.claim.type == ClaimType.BINARY:
            if not isinstance(resolution_input.outcome, bool):
                raise DecisionTrackerError("binary FORECAST outcome must be true or false")
            if decision.claim.probability is None:
                raise DecisionTrackerError("binary FORECAST is missing its committed probability")
            base_rate = decision.reasoning.base_rate.value if decision.reasoning.base_rate else None
            score = score_binary(decision.claim.probability, resolution_input.outcome, base_rate)

        resolved_at = self.now()
        resolution = Resolution(
            resolved_at=resolved_at,
            **resolution_input.model_dump(exclude={"automated"}),
            **score,
            interval_hit=(decision.claim.distribution.p10 <= float(resolution_input.outcome) <= decision.claim.distribution.p90) if decision.claim.type==ClaimType.NUMERIC_INTERVAL and decision.claim.distribution and isinstance(resolution_input.outcome,(int,float)) else None,
        )
        resolved = decision.model_copy(
            update={"status": DecisionStatus.RESOLVED, "resolution": resolution}
        )
        with self.store.connect() as connection:
            with connection:
                self.store.append(connection, resolved, "RESOLVED", resolved_at)
        return resolved

    def void(self,decision_id:str,reason:str)->Decision:
        if not reason.strip():raise DecisionTrackerError("VOID requires a reason")
        d=self.require(decision_id)
        if d.status not in {DecisionStatus.DRAFT,DecisionStatus.LIVE}:raise DecisionTrackerError("only DRAFT or LIVE decisions can be voided")
        result=d.model_copy(update={"status":DecisionStatus.VOID})
        with self.store.connect() as c:
            with c:self.store.append(c,result,"VOIDED",self.now())
        return result

    def supersede(self,decision_id:str,replacement_id:str,reason:str)->Decision:
        if not reason.strip():raise DecisionTrackerError("SUPERSEDED requires a reason")
        old=self.require(decision_id);new=self.require(replacement_id)
        result=old.model_copy(update={"status":DecisionStatus.SUPERSEDED})
        with self.store.connect() as c:
            with c:self.store.append(c,result,"SUPERSEDED",self.now())
        return result

    def amend(self,decision_id:str,changes:dict,reason:str)->Decision:
        if not reason.strip():raise DecisionTrackerError("amendment requires a reason")
        d=self.require(decision_id);allowed={"domain","action"}
        if not set(changes)<=allowed:raise DecisionTrackerError("locked claim/reasoning fields cannot be amended")
        amendment={"at":self.now().isoformat(),"reason":reason,"changes":changes}
        integrity=d.integrity.model_copy(update={"amendments":[*d.integrity.amendments,amendment]})
        result=d.model_copy(update={**changes,"integrity":integrity})
        with self.store.connect() as c:
            with c:self.store.append(c,result,"AMENDED",self.now())
        return result

    def require(self, decision_id: str) -> Decision:
        decision = self.store.get(decision_id)
        if decision is None:
            raise DecisionTrackerError(f"decision not found: {decision_id}")
        return decision

    def rebuild_projection(self) -> int:
        events = self.store.events()
        latest: dict[str, dict] = {}
        occurred: dict[str, str] = {}
        for event in events:
            latest[event.decision_id] = event.payload
            occurred[event.decision_id] = event.occurred_at.isoformat()
        with self.store.connect() as connection:
            with connection:
                connection.execute("DELETE FROM decisions")
                connection.executemany(
                    "INSERT INTO decisions(decision_id, state_json, updated_at) VALUES (?, ?, ?)",
                    [
                        (decision_id, canonical_json(payload), occurred[decision_id])
                        for decision_id, payload in latest.items()
                    ],
                )
        return len(latest)

    @staticmethod
    def _process(draft: DecisionDraft) -> Process:
        reasoning = draft.reasoning
        machine_checkable = bool(draft.claim.resolution_source)
        score = (
            (0.25 if reasoning.base_rate else 0)
            + (0.15 if len(reasoning.alternatives_considered) >= 2 else 0)
            + (0.20 if reasoning.falsifiers else 0)
            + (0.15 if reasoning.premortem else 0)
            + (0.15 if reasoning.source_refs else 0)
            + (0.10 if machine_checkable else 0)
        )
        return Process(
            base_rate_stated=reasoning.base_rate is not None,
            alternatives_count=len(reasoning.alternatives_considered),
            falsifier_named=bool(reasoning.falsifiers),
            premortem_done=bool(reasoning.premortem),
            outside_view_sought=bool(reasoning.source_refs),
            resolution_machine_checkable=machine_checkable,
            process_score=score,
        )

    @staticmethod
    def _gate_failures(decision: Decision) -> list[str]:
        failures: list[str] = []
        claim = decision.claim
        if not claim.resolution_source:
            failures.append("resolution_source is required")
        if not claim.resolution_date and not claim.resolution_triggers:
            failures.append("resolution_date or resolution_trigger is required")
        if claim.probability is None and claim.distribution is None and not claim.success_metric:
            failures.append("probability, distribution, or success_metric is required")
        if not decision.reasoning.falsifiers:
            failures.append("at least one falsifier is required")
        return failures
