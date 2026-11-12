from __future__ import annotations

import os
import time

from gateway.audit import AuditStore
from gateway.policy import PolicyEngine
from gateway.security import PairingStore


class ControlService:
    def __init__(
        self,
        *,
        install_token: str,
        pairings: PairingStore,
        policy: PolicyEngine,
        audit: AuditStore,
    ) -> None:
        self.install_token = install_token
        self.pairings = pairings
        self.policy = policy
        self.audit = audit
        self.started_at = time.time()
        self.glc_enabled = True

    def authenticate(self, authorization: str | None) -> None:
        from fastapi import HTTPException

        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token (Authorization: Bearer <install_token>)")
        if authorization.removeprefix("Bearer ").strip() != self.install_token:
            raise HTTPException(403, "install token mismatch")

    def audit_control(self, event_type: str, *, params: object = None, result: object = None) -> int:
        return self.audit.append(
            channel="control",
            channel_user_id="install-token",
            trust_level="owner_paired",
            event_type=event_type,
            params=params,
            result=result,
        )

    def require_audit_writable(self) -> None:
        """Fail-closed gate for security-relevant control actions.

        Decision #4 (Plan 03) requires a deliberate audit failure policy
        rather than whatever falls out of unhandled exceptions. Mutating
        control actions (pairing, policy reload, kill) must not take effect
        if the audit log cannot record them: this is checked *before* the
        effect is applied, so an unavailable audit store leaves state
        unchanged and the caller gets a clear 503, not a 500 after the fact.
        A failure in the follow-up `audit_control` write itself (the store
        going down in the small window between this check and that write)
        is a residual race, not a designed fail-open — it still surfaces as
        a 500, but the effect will have already committed by then.
        """
        from fastapi import HTTPException

        try:
            self.audit.healthcheck()
        except Exception as exc:
            raise HTTPException(503, f"audit log is unavailable; refusing to record action: {exc}") from exc

    def audit_best_effort(self, event_type: str, *, params: object = None, result: object = None) -> None:
        """Fail-open audit logging for reads that are not security decisions.

        `presence` only reports state; losing its audit trail entry when the
        audit store is briefly unavailable is preferable to making a status
        read unavailable too.
        """
        try:
            self.audit_control(event_type, params=params, result=result)
        except Exception:
            pass

    def reload_policy(self, *, trigger: str) -> None:
        self.require_audit_writable()
        self.policy.reload()
        self.audit_control("policy_reloaded", params={"trigger": trigger}, result={"status": "ok"})

    def suspend_glc(self) -> dict[str, object]:
        """Stop the migrated GLC capability without terminating Gateway.

        Plan 04's LLM service consults this state before accepting work. The
        compatibility response remains stable while ingestion and the shell
        remain alive in the unified process.
        """

        self.require_audit_writable()
        self.glc_enabled = False
        result: dict[str, object] = {"status": "terminating", "pid": os.getpid()}
        self.audit_control("glc_suspended", result=result)
        return result
