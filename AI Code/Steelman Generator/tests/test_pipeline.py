from steelman.models import ProponentStatus, Source, SourceTier, VerificationGrade
from steelman.pipeline import SteelmanPipeline


def test_pipeline_constructs_and_downgrades_without_evidence():
    run = SteelmanPipeline().run("Margins will improve", "Acme", "within 12 months")
    assert run.proponent_status == ProponentStatus.CONSTRUCTED
    assert run.graph.warnings
    empirical = [result for result in run.graph.verifications if result.grade != VerificationGrade.NOT_APPLICABLE]
    assert empirical[0].grade == VerificationGrade.UNSUPPORTED


def test_pipeline_records_named_proponent_and_primary_support():
    source = Source(
        title="Margin outlook",
        author_or_advocate="Jane Doe",
        excerpt="Observed conditions within Acme are consistent with margins improving over twelve months.",
        tier=SourceTier.PRIMARY,
    )
    run = SteelmanPipeline().run("Margins will improve", "Acme", "within 12 months", [source])
    assert run.proponent_status == ProponentStatus.SOURCED
    assert run.proponent_names == ["Jane Doe"]
    empirical = [result for result in run.graph.verifications if result.grade != VerificationGrade.NOT_APPLICABLE]
    assert empirical[0].grade == VerificationGrade.PRIMARY

