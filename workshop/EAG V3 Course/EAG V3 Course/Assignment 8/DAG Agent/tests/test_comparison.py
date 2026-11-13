import copy
import json

import pytest

from agent.comparison import compare, validate_request


@pytest.fixture
def comparison_request():
    return {
        "question": "Compare three plans on yearly cost and support.",
        "criteria": [
            {"id": "cost", "label": "Annual cost", "kind": "number",
             "unit": "INR/year", "direction": "lower"},
            {"id": "support", "label": "Support", "kind": "text"}],
        "options": [
            {"id": "a", "name": "Plan A", "sources": [
                {"id": "sa", "text": "Costs INR 100 per month. Email support.",
                 "as_of": "2026-01-01"}], "evidence": {
                "cost": {"value": 100, "unit": "INR/month", "source": "sa",
                         "quote": "Costs INR 100 per month."},
                "support": {"value": "Email", "source": "sa", "quote": "Email support."}}},
            {"id": "b", "name": "Plan B", "sources": [
                {"id": "sb", "text": "Costs INR 1500 per year. Phone support.",
                 "as_of": "2026-01-01"}], "evidence": {
                "cost": {"value": 1500, "unit": "INR/year", "source": "sb",
                         "quote": "Costs INR 1500 per year."},
                "support": {"value": "Phone", "source": "sb", "quote": "Phone support."}}},
            {"id": "c", "name": "Plan C", "sources": [
                {"id": "sc", "text": "Costs INR 900 per year.", "as_of": "2026-01-01"}],
             "evidence": {"cost": {"value": 900, "unit": "INR/year", "source": "sc",
                                   "quote": "Costs INR 900 per year."}}}],
    }


def test_cross_domain_comparison_normalizes_cost_and_preserves_missing(comparison_request):
    request = comparison_request
    original = copy.deepcopy(request)
    result = compare(request)
    assert result["cells"]["a"]["cost"]["value"] == 1200
    assert result["cells"]["c"]["support"]["status"] == "missing"
    assert result["findings"]["cost"]["best"] == ["c"]
    assert result["findings"]["cost"]["range"] == 600
    assert result["ranking"] is None
    assert request == original


def test_fabricated_quote_is_rejected(comparison_request):
    request = comparison_request
    request["options"][0]["evidence"]["cost"]["quote"] = "Costs INR 10 per month."
    with pytest.raises(ValueError, match="passage"):
        compare(request)


def test_value_must_be_present_in_verified_passage(comparison_request):
    request = comparison_request
    request["options"][0]["evidence"]["cost"]["value"] = 10
    with pytest.raises(ValueError, match="value"):
        compare(request)


def test_incompatible_units_are_visible_and_not_ranked(comparison_request):
    request = comparison_request
    request["options"][0]["evidence"]["cost"]["unit"] = "USD/year"
    result = compare(request)
    assert result["cells"]["a"]["cost"]["status"] == "incomparable"
    assert result["findings"]["cost"]["best"] == []


def test_conflicting_values_are_not_silently_resolved(comparison_request):
    request = comparison_request
    option = request["options"][0]
    option["sources"].append({"id": "sa2", "text": "Costs INR 200 per month.",
                              "as_of": "2026-01-01"})
    option["evidence"]["cost"] = [option["evidence"]["cost"],
        {"value": 200, "unit": "INR/month", "source": "sa2",
         "quote": "Costs INR 200 per month."}]
    result = compare(request)
    assert result["cells"]["a"]["cost"]["status"] == "conflict"
    assert len(result["cells"]["a"]["cost"]["observations"]) == 2


def test_different_dates_block_best_claim(comparison_request):
    request = comparison_request
    request["options"][0]["sources"][0]["as_of"] = "2024-01-01"
    result = compare(request)
    assert result["findings"]["cost"]["best"] == []
    assert any("dates" in warning for warning in result["warnings"])


def test_explicit_weights_require_complete_comparable_numeric_data(comparison_request):
    request = comparison_request
    request["criteria"][0]["weight"] = 1
    result = compare(request)
    assert [r["option"] for r in result["ranking"]] == ["c", "a", "b"]
    request["options"][0]["evidence"].pop("cost")
    assert compare(request)["ranking"] is None


def test_unknown_reference_and_duplicate_ids_fail_early(comparison_request):
    request = comparison_request
    request["options"][0]["evidence"]["cost"]["source"] = "invented"
    with pytest.raises(ValueError, match="source"):
        compare(request)
    request["options"][1]["id"] = "a"
    with pytest.raises(ValueError, match="unique"):
        validate_request(request)


def test_nonfinite_or_boolean_numeric_values_are_rejected(comparison_request):
    request = comparison_request
    for value in (True, float("nan"), float("inf")):
        request["options"][0]["evidence"]["cost"]["value"] = value
        with pytest.raises(ValueError):
            compare(request)


def test_same_engine_compares_textual_documents(comparison_request):
    request = comparison_request
    request["criteria"] = [request["criteria"][1]]
    for option in request["options"]:
        option["evidence"].pop("cost")
    result = compare(request)
    assert result["cells"]["b"]["support"]["value"] == "Phone"
    assert result["ranking"] is None


def test_one_document_can_support_multiple_options(comparison_request):
    request = comparison_request
    shared = {"id": "shared", "text": "Plan A costs INR 100 per month. Plan B costs INR 1500 per year.",
              "as_of": "2026-01-01"}
    for option in request["options"][:2]:
        option["sources"] = [dict(shared)]
        option["evidence"].pop("support")
        option["evidence"]["cost"]["source"] = "shared"
    result = compare(request)
    assert result["cells"]["a"]["cost"]["value"] == 1200


def test_monthly_price_cannot_be_relabelled_annual(comparison_request):
    request = comparison_request
    request["options"][0]["evidence"]["cost"]["unit"] = "INR/year"
    with pytest.raises(ValueError, match="period"):
        compare(request)


def test_extractor_cannot_invent_as_of_date(comparison_request):
    request = comparison_request
    request["options"][0]["evidence"]["cost"]["as_of"] = "2030-01-01"
    with pytest.raises(ValueError, match="date"):
        compare(request)
