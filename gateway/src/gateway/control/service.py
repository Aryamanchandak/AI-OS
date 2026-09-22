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

    def reload_policy(self, *, trigger: str) -> None:
        self.policy.reload()
        self.audit_control("policy_reloaded", params={"trigger": trigger}, result={"status": "ok"})

    def suspend_glc(self) -> dict[str, object]:
        """Stop the migrated GLC capability without terminating Gateway.

        Plan 04's LLM service consults this state before accepting work. The
        compatibility response remains stable while ingestion and the shell
        remain alive in the unified process.
        """

        self.glc_enabled = False
        result: dict[str, object] = {"status": "terminating", "pid": os.getpid()}
        self.audit_control("glc_suspended", result=result)
        return result
