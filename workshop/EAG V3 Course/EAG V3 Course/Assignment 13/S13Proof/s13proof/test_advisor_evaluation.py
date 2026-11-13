"""The retrieval comparison uses immutable source labels, not model judgments."""
from s13proof.advisor_evaluation import evaluate


def test_ten_labeled_queries_compare_complete_evidence_and_report_context_cost():
    result = evaluate()
    assert result["queries"] == 10
    assert len(result["corpus_sha256"]) == 5
    assert result["semantic"]["complete_evidence_at_3"] == 10
    assert result["semantic"]["complete_evidence_at_3"] > result["fixed_40_words"]["complete_evidence_at_3"]
    assert result["semantic"]["mean_retrieved_words"] > result["fixed_40_words"]["mean_retrieved_words"]
    assert all(row["label_present"] for row in result["cases"])
    assert all(row["coverage_exact"] and row["reindex_idempotent"] for row in result["documents"])
