import json

import pytest

from steelman.forensics import GENERIC_FLAGS, assess_forensic_flag, load_flag_definitions
from steelman.models import VerificationGrade


def _assessment(**overrides):
    values = {
        "company": "Acme",
        "flag_code": "SA01",
        "observation": "Quarter-end sales rose sharply.",
        "benign_explanation": "A scheduled product launch concentrated ordinary shipments near quarter end.",
        "management_evidence": "Management supplied dated customer orders and shipping records.",
        "contradictory_evidence": "",
        "residual_risk": "Returns after quarter end remain untested.",
        "verification_grade": VerificationGrade.PRIMARY,
        "escalate_requested": True,
    }
    values.update(overrides)
    return assess_forensic_flag(**values)


def test_complete_steelman_allows_requested_escalation():
    assert _assessment().escalation_allowed is True


def test_thin_benign_case_blocks_escalation():
    result = _assessment(benign_explanation="Could be timing.")
    assert result.escalation_allowed is False
    assert result.gate_reasons


def test_custom_catalog_requires_all_fifteen_unique_codes(tmp_path):
    valid = tmp_path / "flags.json"
    valid.write_text(json.dumps([flag.model_dump() for flag in GENERIC_FLAGS]))
    assert len(load_flag_definitions(valid)) == 15
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps([GENERIC_FLAGS[0].model_dump()]))
    with pytest.raises(ValueError, match="SA01 through SA15"):
        load_flag_definitions(invalid)
