from steelman.forensics import assess_forensic_flag
from steelman.models import VerificationGrade
from steelman.pipeline import SteelmanPipeline
from steelman.storage import SQLiteStore


def test_analysis_round_trip_and_graph_tables(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")
    run = SteelmanPipeline().run("Cash flow will improve", "Acme", "next year")
    store.save_analysis(run)
    loaded = store.get_analysis(run.id)
    assert loaded == run
    assert store.list_analyses()[0]["id"] == run.id


def test_forensic_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")
    assessment = assess_forensic_flag(
        company="Acme",
        flag_code="SA04",
        observation="Profit and cash diverged.",
        benign_explanation="Seasonal inventory purchases preceded a contracted customer delivery cycle.",
        management_evidence="Management provided the purchase and delivery schedule.",
        contradictory_evidence="",
        residual_risk="The customer acceptance date remains uncertain.",
        verification_grade=VerificationGrade.SECONDARY,
        escalate_requested=False,
    )
    store.save_forensic_assessment(assessment)
    assert store.list_forensic_assessments() == [assessment]

