"""Atomic budget reservation and actual-cost reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
from pathlib import Path
import sqlite3
import time
import uuid
from typing import Any

import yaml

from gateway.llm.economics.meter import DIMENSIONS, Principal

VALID_PERIODS = ("minute", "hour", "day", "month", "lifetime")
BUDGET_EXCEEDED = "budget_exceeded"


class BudgetConfigError(ValueError): pass


def _period_start(period: str, now: float | None = None) -> float:
    value = now or time.time()
    seconds = {"minute": 60, "hour": 3600, "day": 86400, "month": 2_592_000}.get(period)
    return 0.0 if seconds is None else value - value % seconds


def _parse_principal(spec: str) -> tuple[str, str]:
    dimension, sep, pattern = str(spec).partition(":")
    if not sep or dimension not in DIMENSIONS or not pattern.strip():
        raise BudgetConfigError(f"principal {spec!r}: expected <dimension>:<value> with dimension in {list(DIMENSIONS)}")
    return dimension, pattern.strip()


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    principal: str; dimension: str; pattern: str; limit_usd: float
    period: str = "day"; include_errors: bool = True; source: str = "budgets.yaml"
    def matches(self, dimension: str, value: str) -> bool: return dimension == self.dimension and fnmatch.fnmatch(value, self.pattern)
    def as_dict(self) -> dict[str, Any]: return {name: getattr(self, name) for name in ("principal", "dimension", "pattern", "limit_usd", "period", "include_errors", "source")}


@dataclass(slots=True)
class BudgetStatus:
    principal: str; dimension: str; value: str; limit_usd: float; spent_usd: float
    period: str; period_start: float; source: str; reserved_usd: float = 0.0
    @property
    def remaining_usd(self) -> float: return max(0.0, self.limit_usd - self.spent_usd - self.reserved_usd)
    @property
    def fraction_used(self) -> float: return 1.0 if self.limit_usd <= 0 else min(1.0, (self.spent_usd + self.reserved_usd) / self.limit_usd)
    def as_dict(self) -> dict[str, Any]: return {"principal": self.principal, "dimension": self.dimension, "value": self.value, "limit_usd": round(self.limit_usd, 8), "spent_usd": round(self.spent_usd, 8), "reserved_usd": round(self.reserved_usd, 8), "remaining_usd": round(self.remaining_usd, 8), "fraction_used": round(self.fraction_used, 6), "period": self.period, "period_start": self.period_start, "source": self.source}


@dataclass(slots=True)
class Admission:
    allowed: bool; projected_usd: float; reservation_id: str | None = None
    checked: list[BudgetStatus] = field(default_factory=list); breached: BudgetStatus | None = None
    reason: str = ""; enforced: bool = True
    def envelope(self) -> dict[str, Any]:
        item = self.breached
        return {"error": BUDGET_EXCEEDED, "code": BUDGET_EXCEEDED, "message": self.reason, "principal": item.principal if item else None, "dimension": item.dimension if item else None, "period": item.period if item else None, "period_start": item.period_start if item else None, "limit_usd": round(item.limit_usd, 8) if item else None, "spent_usd": round(item.spent_usd, 8) if item else None, "remaining_usd": round(item.remaining_usd, 8) if item else None, "projected_usd": round(self.projected_usd, 8), "shortfall_usd": round(max(0.0, self.projected_usd - (item.remaining_usd if item else 0)), 8), "checked": [x.as_dict() for x in self.checked], "hint": "The call was refused before any provider was contacted. Lower max_tokens, choose a cheaper model, or raise the ceiling with POST /v1/budget."}
    def as_dict(self) -> dict[str, Any]: return {"allowed": self.allowed, "enforced": self.enforced, "projected_usd": round(self.projected_usd, 8), "reservation_id": self.reservation_id, "reason": self.reason, "checked": [x.as_dict() for x in self.checked], "breached": self.breached.as_dict() if self.breached else None}


_SCHEMA = """CREATE TABLE IF NOT EXISTS llm_budget_limits (principal TEXT PRIMARY KEY, dimension TEXT NOT NULL, pattern TEXT NOT NULL, limit_usd REAL NOT NULL, period TEXT NOT NULL, include_errors INTEGER NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS llm_budget_entries (id INTEGER PRIMARY KEY, reservation_id TEXT NOT NULL, dimension TEXT NOT NULL, value TEXT NOT NULL, period_start REAL NOT NULL, amount_usd REAL NOT NULL, state TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_llm_budget_entries ON llm_budget_entries(dimension,value,period_start,state);"""


class BudgetController:
    def __init__(self, path: Path, database_path: Path, *, load_overrides: bool = True) -> None:
        self.path, self.database_path, self.load_overrides = path, database_path, load_overrides
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if raw.get("version") != 1: raise BudgetConfigError(f"{path}: version must be 1")
        self.defaults = raw.get("defaults") or {}; self.projection = raw.get("projection") or {}; self.alerts = raw.get("alerts") or {}
        entries = raw.get("policies") or []
        if not isinstance(entries, list): raise BudgetConfigError("budgets.yaml: policies must be a list")
        self.file_policies = [self._policy(x, str(path)) for x in entries]
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection: connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None, check_same_thread=False); connection.row_factory = sqlite3.Row; return connection

    def _policy(self, entry: dict[str, Any], source: str) -> BudgetPolicy:
        dimension, pattern = _parse_principal(str(entry.get("principal", ""))); limit = float(entry.get("limit_usd", -1)); period = str(entry.get("period", self.defaults.get("period", "day")))
        if limit < 0 or period not in VALID_PERIODS: raise BudgetConfigError(f"invalid budget policy {entry!r}")
        return BudgetPolicy(f"{dimension}:{pattern}", dimension, pattern, limit, period, bool(entry.get("include_errors", self.defaults.get("include_errors", True))), source)

    @property
    def enabled(self) -> bool: return bool(self.defaults.get("enabled", True))

    def policies(self) -> list[BudgetPolicy]:
        merged = {x.principal: x for x in self.file_policies}
        if self.load_overrides:
            with self._connect() as connection:
                for row in connection.execute("SELECT * FROM llm_budget_limits"):
                    merged[row["principal"]] = BudgetPolicy(row["principal"], row["dimension"], row["pattern"], float(row["limit_usd"]), row["period"], bool(row["include_errors"]), "runtime")
        return list(merged.values())

    def policy_for(self, dimension: str, value: str) -> BudgetPolicy | None:
        matches = [x for x in self.policies() if x.matches(dimension, value)]
        return max(matches, key=lambda x: (not any(c in x.pattern for c in "*?["), len(x.pattern))) if matches else None

    def _status_in(self, connection: sqlite3.Connection, policy: BudgetPolicy, value: str) -> BudgetStatus:
        start = _period_start(policy.period)
        rows = connection.execute("SELECT state, COALESCE(SUM(amount_usd),0) amount FROM llm_budget_entries WHERE dimension=? AND value=? AND period_start>=? GROUP BY state", (policy.dimension, value, start)).fetchall()
        amounts = {row["state"]: float(row["amount"]) for row in rows}
        return BudgetStatus(f"{policy.dimension}:{value}", policy.dimension, value, policy.limit_usd, amounts.get("actual", 0.0), policy.period, start, policy.source, amounts.get("reserved", 0.0))

    def status_for(self, dimension: str, value: str) -> BudgetStatus | None:
        policy = self.policy_for(dimension, value)
        if policy is None: return None
        with self._connect() as connection: return self._status_in(connection, policy, value)

    def admit(self, principal: Principal, projected_usd: float) -> Admission:
        if not self.enabled: return Admission(True, projected_usd, enforced=False, reason="budget enforcement disabled")
        matches = [(policy, value) for dimension, value in principal.present().items() if (policy := self.policy_for(dimension, value)) is not None]
        if not matches: return Admission(True, projected_usd, reason="no budget policy matches this principal")
        reservation_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                statuses = [self._status_in(connection, policy, value) for policy, value in matches]
                breached = min((x for x in statuses if x.spent_usd + x.reserved_usd + projected_usd > x.limit_usd), key=lambda x: x.remaining_usd, default=None)
                if breached:
                    connection.rollback(); return Admission(False, projected_usd, checked=statuses, breached=breached, reason=f"{breached.principal} would exceed its {breached.period} budget")
                now = time.time()
                connection.executemany("INSERT INTO llm_budget_entries(reservation_id,dimension,value,period_start,amount_usd,state,created_at) VALUES(?,?,?,?,?,'reserved',?)", [(reservation_id, policy.dimension, value, _period_start(policy.period, now), projected_usd, now) for policy, value in matches])
                connection.commit(); return Admission(True, projected_usd, reservation_id=reservation_id, checked=statuses, reason="within budget")
            except BaseException: connection.rollback(); raise

    def reconcile(self, reservation_id: str | None, actual_usd: float, *, count: bool = True) -> None:
        if not reservation_id: return
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state, amount = ("actual", max(0.0, actual_usd)) if count else ("released", 0.0)
            connection.execute("UPDATE llm_budget_entries SET state=?, amount_usd=? WHERE reservation_id=? AND state='reserved'", (state, amount, reservation_id)); connection.commit()

    def set_limit(self, principal: str, limit_usd: float, period: str | None = None, include_errors: bool | None = None) -> BudgetPolicy:
        policy = self._policy({"principal": principal, "limit_usd": limit_usd, "period": period or self.defaults.get("period", "day"), "include_errors": self.defaults.get("include_errors", True) if include_errors is None else include_errors}, "runtime")
        with self._connect() as connection: connection.execute("INSERT INTO llm_budget_limits VALUES(?,?,?,?,?,?,?) ON CONFLICT(principal) DO UPDATE SET limit_usd=excluded.limit_usd,period=excluded.period,include_errors=excluded.include_errors,updated_at=excluded.updated_at", (policy.principal, policy.dimension, policy.pattern, policy.limit_usd, policy.period, int(policy.include_errors), time.time()))
        return policy

    def clear_limit(self, principal: str) -> bool:
        dimension, pattern = _parse_principal(principal)
        with self._connect() as connection: result = connection.execute("DELETE FROM llm_budget_limits WHERE principal=?", (f"{dimension}:{pattern}",))
        return result.rowcount > 0

    def describe(self) -> dict[str, Any]: return {"path": str(self.path), "enabled": self.enabled, "defaults": self.defaults, "projection": self.projection, "alerts": self.alerts, "policies": [x.as_dict() for x in self.policies()]}
