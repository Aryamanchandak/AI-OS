from __future__ import annotations

import json
from pathlib import Path

from steelman.models import ForensicAssessment, ForensicFlagDefinition, VerificationGrade


GENERIC_FLAGS = [
    ForensicFlagDefinition(code="SA01", name="Revenue recognition", prompt="Could timing, cut-off, or contract terms explain the anomaly?"),
    ForensicFlagDefinition(code="SA02", name="Receivables quality", prompt="Could customer mix or billing cycles explain the receivables movement?"),
    ForensicFlagDefinition(code="SA03", name="Inventory movement", prompt="Could planned stocking, seasonality, or supply constraints explain the change?"),
    ForensicFlagDefinition(code="SA04", name="Cash-flow divergence", prompt="Could working-capital timing explain the profit-to-cash divergence?"),
    ForensicFlagDefinition(code="SA05", name="Capitalized costs", prompt="Could the costs meet a consistently applied capitalization policy?"),
    ForensicFlagDefinition(code="SA06", name="Non-recurring adjustments", prompt="Could the adjustment be genuinely unusual and transparently reconciled?"),
    ForensicFlagDefinition(code="SA07", name="Related-party activity", prompt="Could the transaction be arm's-length, disclosed, and economically necessary?"),
    ForensicFlagDefinition(code="SA08", name="Acquisition accounting", prompt="Could purchase accounting or integration timing explain the signal?"),
    ForensicFlagDefinition(code="SA09", name="Margin discontinuity", prompt="Could product mix, pricing, or input costs explain the margin shift?"),
    ForensicFlagDefinition(code="SA10", name="Tax-rate anomaly", prompt="Could jurisdiction mix or discrete tax items explain the effective rate?"),
    ForensicFlagDefinition(code="SA11", name="Debt and liquidity", prompt="Could committed facilities or ordinary refinancing explain the apparent pressure?"),
    ForensicFlagDefinition(code="SA12", name="Auditor or control change", prompt="Could normal rotation, growth, or remediation explain the governance event?"),
    ForensicFlagDefinition(code="SA13", name="Management incentives", prompt="Could compensation reflect legitimate retention or performance design?"),
    ForensicFlagDefinition(code="SA14", name="Segment or KPI changes", prompt="Could business evolution justify the reporting-definition change?"),
    ForensicFlagDefinition(code="SA15", name="Disclosure inconsistency", prompt="Could immateriality, timing, or drafting explain the inconsistency?"),
]


def load_flag_definitions(path: str | Path | None = None) -> list[ForensicFlagDefinition]:
    if path is None:
        return list(GENERIC_FLAGS)
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    flags = [ForensicFlagDefinition.model_validate(item) for item in raw]
    codes = [flag.code for flag in flags]
    required = {f"SA{number:02d}" for number in range(1, 16)}
    if set(codes) != required or len(codes) != len(required):
        raise ValueError("A custom forensic catalog must define each unique code SA01 through SA15")
    return flags


def get_flag(code: str, flags: list[ForensicFlagDefinition] | None = None) -> ForensicFlagDefinition:
    try:
        return next(flag for flag in (flags or GENERIC_FLAGS) if flag.code == code)
    except StopIteration as exc:
        raise ValueError(f"Unknown forensic flag: {code}") from exc


def assess_forensic_flag(
    *,
    company: str,
    flag_code: str,
    observation: str,
    benign_explanation: str,
    management_evidence: str,
    contradictory_evidence: str,
    residual_risk: str,
    verification_grade: VerificationGrade,
    escalate_requested: bool,
    flag_definitions: list[ForensicFlagDefinition] | None = None,
) -> ForensicAssessment:
    get_flag(flag_code, flag_definitions)
    reasons: list[str] = []
    if len(benign_explanation.strip()) < 30:
        reasons.append("A substantive benign-management explanation is required (at least 30 characters).")
    if not management_evidence.strip():
        reasons.append("Management-supporting evidence must be considered, even if none was found.")
    if not residual_risk.strip():
        reasons.append("Residual risk after the steelman must be stated.")
    if verification_grade == VerificationGrade.NOT_APPLICABLE:
        reasons.append("Choose an evidence grade for the benign explanation.")
    allowed = escalate_requested and not reasons
    return ForensicAssessment(
        company=company.strip(),
        flag_code=flag_code,
        observation=observation.strip(),
        benign_explanation=benign_explanation.strip(),
        management_evidence=management_evidence.strip(),
        contradictory_evidence=contradictory_evidence.strip(),
        residual_risk=residual_risk.strip(),
        verification_grade=verification_grade,
        escalate_requested=escalate_requested,
        escalation_allowed=allowed,
        gate_reasons=reasons,
    )
