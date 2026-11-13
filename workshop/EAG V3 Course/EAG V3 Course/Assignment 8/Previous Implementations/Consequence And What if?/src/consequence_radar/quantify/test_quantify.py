from decimal import Decimal

from consequence_radar.models import Estimate
from consequence_radar.quantify import convert_currency, multiply_range, sensitivity


def test_decimal_formula_currency_record_and_sensitivity():
    base = Estimate(id="Q1", metric="Volume", estimate_type="source_range", low=Decimal("10.0"), central=Decimal("12.0"), high=Decimal("14.0"), unit="tonnes", source_claim_ids=["C1"], caveat="source range")
    price = Estimate(id="Q2", metric="Price", estimate_type="source_range", low=Decimal("2.5"), central=Decimal("3.0"), high=Decimal("3.5"), unit="USD/tonne", currency="USD", source_claim_ids=["C2"], caveat="source range")
    result = multiply_range(estimate_id="Q3", metric="Revenue", left=base, right=price, unit="USD", currency="USD", caveat="multiplication")
    assert result.low == Decimal("25.00") and result.high == Decimal("49.00") and result.formula == "Q1 * Q2"
    fx = Estimate(id="FX", metric="USD/INR", estimate_type="source_range", low=Decimal("82"), central=Decimal("83"), high=Decimal("84"), unit="INR/USD", source_claim_ids=["C3"], caveat="spot range")
    converted = convert_currency(result, estimate_id="Q4", fx=fx, target_currency="INR")
    assert converted.currency == "INR" and converted.input_estimate_ids == ["Q3", "FX"]
    assert sensitivity(base, price)["central"] == Decimal("36.00")
