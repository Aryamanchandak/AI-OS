import json

import pytest

from agent.comparison import compare
from agent.interpretation import render_interpretation
from tests.test_comparison import comparison_request


def test_interpretation_is_labelled_and_links_exact_evidence(comparison_request):
    result = compare(comparison_request)
    payload = {"notes": [{"text": "Phone support may matter if you need synchronous help.",
                          "basis": [{"source": "sb", "quote": "Phone support."}]}]}
    rendered = render_interpretation(json.dumps(payload), result)
    assert "Inference:" in rendered and "[sb]" in rendered
    payload["notes"][0]["basis"][0]["quote"] = "24-hour phone support."
    with pytest.raises(ValueError, match="absent passage"):
        render_interpretation(json.dumps(payload), result)
