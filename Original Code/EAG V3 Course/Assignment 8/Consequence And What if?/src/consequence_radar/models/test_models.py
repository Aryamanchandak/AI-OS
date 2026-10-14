from decimal import Decimal

import pytest
from pydantic import ValidationError

from consequence_radar.models import Estimate, NewsBatch


def test_batch_cardinality_and_decimal_preservation():
    with pytest.raises(ValidationError): NewsBatch(items=[])
    estimate = Estimate(id="Q", metric="range", estimate_type="derived_range", low=Decimal("0.1"), central=Decimal("0.2"), high=Decimal("0.3"), formula="A*B", input_estimate_ids=["A","B"], caveat="test")
    assert estimate.model_dump_json().count("0.1") == 1
