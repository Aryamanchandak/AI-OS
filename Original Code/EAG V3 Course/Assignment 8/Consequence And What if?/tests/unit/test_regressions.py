"""Regressions for defects that no earlier test covered.

Each case here failed a run that should have succeeded, or passed one that
should have failed, before the accompanying fix.
"""

import threading
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from consequence_radar.cases import CaseSelectionError, validate_cases
from consequence_radar.config import Settings
from consequence_radar.evidence import verify_claims
from consequence_radar.models import (
    CandidateSeed, Case, CaseSelection, EvidenceClaim, EvidenceClaimDraft, FactualStatus,
    NewsBatch, NewsItem, NewsletterReport, SELECTION_DIMENSIONS, SourceRecord,
)
from consequence_radar.providers.fetch import UnsafeUrl, normalize_url
from consequence_radar.report import validate_report
from consequence_radar.report_context import (
    CLAIM_PASSAGE_EXCERPT_CHARS, SOURCE_EXCERPT_CHARS, approximate_tokens, compile_context,
)
from consequence_radar.storage import Repository
from consequence_radar.web.app import TERMINAL, create_app


def seed():
    return CandidateSeed(id="X", source_item_ids=["N"], reported_premise="Policy announced",
                         factual_status=FactualStatus.ANNOUNCEMENT, possible_immediate_effect="Imported cost changes",
                         possible_indian_equity_route="Indian sector EBITDA",
                         grades={k: "high" for k in SELECTION_DIMENSIONS}, rationale="Strong route")


def central_case():
    return Case(id="K1", name="Cost compression", path_node_ids=["N0", "N1", "N2"], path_edge_ids=["E1", "E2"],
                required_assumption_ids=["A1"], supporting_claim_ids=["C1"], contradicting_claim_ids=[],
                equity_implication_direction="negative", estimate_ids=["Q1"], quantification_status="directional_only",
                time_horizon="12 months", weakening_observation="Policy delayed", central=True)


def article(body: str) -> NewsletterReport:
    return NewsletterReport(headline="Impact", dek="A careful consequence",
                            why_this_matters="This matters because Indian sector earnings absorb the cost.",
                            article_markdown=body,
                            central_case_summary="The supported mechanism makes this the coherent central path.",
                            key_assumptions=["The policy is implemented on schedule"],
                            what_changes_the_view=["Delay"], source_ids_used=["S1"])


def context_for(graph, sources, claims, budget=24000):
    return compile_context(seed=seed(), graph=graph, cases=CaseSelection(central_case=central_case()),
                           claims=claims, sources=sources, findings=[], decisions=[], gaps=[], failures=[],
                           token_budget=budget)


def claim(cid="C1", source_id="S1"):
    return EvidenceClaim(id=cid, source_id=source_id, claim="Policy announced", exact_passage="Policy announced today",
                         claim_type="fact", stance="supports", concepts=[], passage_verified=True)


# --- report context budget ------------------------------------------------

def test_full_article_bodies_do_not_exhaust_the_report_context_budget(graph):
    """A fetched body is up to 80k characters -- roughly 20k approximate tokens,
    most of the default budget on its own. Every claim here is load-bearing, so
    trimming background evidence cannot rescue the budget: only excerpting the
    bodies can."""
    sources = [SourceRecord(id=f"S{i}", url=f"https://e{i}.example.com/a", title="Official",
                            publisher=f"e{i}.example.com", extracted_text="word " * 16000) for i in range(1, 9)]
    claims = [claim(f"C{i}", f"S{i}") for i in range(1, 9)]
    cases = CaseSelection(central_case=central_case().model_copy(
        update={"supporting_claim_ids": [c.id for c in claims]}))
    context = compile_context(seed=seed(), graph=graph, cases=cases, claims=claims, sources=sources,
                              findings=[], decisions=[], gaps=[], failures=[], token_budget=24000)
    assert len(context.sources) == 8
    assert approximate_tokens(context) < 24000
    assert all(len(s.extracted_text) <= SOURCE_EXCERPT_CHARS for s in context.sources)


def test_a_busy_graph_of_load_bearing_claims_still_fits_the_budget(graph):
    """Once source bodies are excerpted, exact_passage becomes the largest term.
    Every claim here is cited by an active edge, so dropping background evidence
    cannot recover the budget -- only excerpting the passage can."""
    edges = [graph.edges[0].model_copy(update={"id": f"E{i}", "supporting_claim_ids": [f"C{i}", f"C{i + 40}"]})
             for i in range(1, 17)]
    busy = graph.model_copy(update={"edges": [*graph.edges, *edges]})
    claims = [EvidenceClaim(id=f"C{i}", source_id=f"S{(i % 14) + 1}", claim="c" * 200, exact_passage="p" * 900,
                            claim_type="fact", stance="supports", concepts=["a"], passage_verified=True)
              for i in range(1, 57)]
    sources = [SourceRecord(id=f"S{i}", url=f"https://e{i}.example.com/a", title="Official",
                            publisher=f"e{i}.example.com", extracted_text="word " * 16000) for i in range(1, 15)]
    context = context_for(busy, sources, claims)
    assert approximate_tokens(context) < 24000
    assert all(len(c.exact_passage) <= CLAIM_PASSAGE_EXCERPT_CHARS
               for c in context.accepted_claims + context.contradicting_claims)


# --- report validation ----------------------------------------------------

def test_bracketed_prose_is_not_read_as_an_invented_citation(graph):
    """[SEBI] and [Sensex] are ordinary words in an Indian-equities article."""
    context = context_for(graph, [SourceRecord(id="S1", url="https://e.com", title="Official", publisher="e.com",
                                               extracted_text="Policy announced today")], [claim()])
    body = ("careful analysis " * 55) + " The regulator [SEBI] and the [Sensex] both matter [S1]."
    assert validate_report(article(body), context, 50, 200) == []


def test_invented_and_lowercase_source_markers_still_fail(graph):
    context = context_for(graph, [SourceRecord(id="S1", url="https://e.com", title="Official", publisher="e.com",
                                               extracted_text="Policy announced today")], [claim()])
    invented = validate_report(article(("careful analysis " * 55) + " [S404]"), context, 50, 200)
    assert any("unknown source" in e for e in invented)
    # A lower-case marker is normalised, not silently ignored as prose.
    assert validate_report(article(("careful analysis " * 55) + " [s1]"), context, 50, 200) == []


def test_reflowed_assumption_statement_is_not_a_mismatch(graph):
    context = context_for(graph, [SourceRecord(id="S1", url="https://e.com", title="Official", publisher="e.com",
                                               extracted_text="Policy announced today")], [claim()])
    report = article(("careful analysis " * 55) + " [S1]").model_copy(
        update={"key_assumptions": ["The policy is  implemented\non schedule "]})
    assert validate_report(report, context, 50, 200) == []


# --- evidence verification ------------------------------------------------

def test_unusable_claim_is_rejected_rather_than_failing_the_run():
    source = SourceRecord(id="S1", url="https://e.com", title="S", publisher="e.com",
                          extracted_text="Revenue increased by 12 percent in the quarter.")
    drafts = [EvidenceClaimDraft(source_id="S1", claim="   ", exact_passage="Revenue increased by 12 percent in the quarter.",
                                claim_type="fact", stance="supports"),
              EvidenceClaimDraft(source_id="S1", claim="Revenue rose", exact_passage="Revenue increased by 12 percent in the quarter.",
                                 claim_type="fact", stance="supports")]
    accepted, rejected = verify_claims(drafts, [source])
    assert [c.id for c in accepted] == ["C1"] and len(rejected) == 1


# --- case validation ------------------------------------------------------

def test_case_citing_an_unverified_claim_fails_closed(graph):
    selection = CaseSelection(central_case=central_case())
    validate_cases(selection, graph, {"C1"})
    with pytest.raises(CaseSelectionError):
        validate_cases(selection, graph, {"C7"})


def test_case_path_nodes_must_exist_in_the_graph(graph):
    ghost = central_case().model_copy(update={"path_node_ids": ["N0", "N404"]})
    with pytest.raises(CaseSelectionError):
        validate_cases(CaseSelection(central_case=ghost), graph, {"C1"})


# --- URL normalisation ----------------------------------------------------

@pytest.mark.parametrize("url", ["http://example..com/a", "http://host:99999/p", "http://[::1]/x", "ftp://example.com/a"])
def test_malformed_urls_are_reported_as_unsafe_not_as_internal_errors(url):
    with pytest.raises(UnsafeUrl):
        normalize_url(url)


# --- configuration --------------------------------------------------------

def test_inverted_report_word_bounds_are_rejected_at_startup():
    with pytest.raises(ValidationError):
        Settings(report_min_words=1200, report_max_words=800)


# --- storage --------------------------------------------------------------

def test_artifact_lookup_distinguishes_version_zero_from_latest(tmp_path, graph):
    repo = Repository(f"sqlite:///{tmp_path / 'v.db'}"); repo.init_schema()
    run_id = repo.create_run(NewsBatch(items=[NewsItem(url="https://example.com/news")]))
    repo.save_artifact(run_id, "graph", graph, version=0)
    repo.save_artifact(run_id, "graph", graph.model_copy(update={"version": 5}), version=5)
    assert repo.artifact(run_id, "graph", version=0)["version"] == 1
    assert repo.artifact(run_id, "graph")["version"] == 5


# --- event stream ---------------------------------------------------------

class WorkingPipeline:
    """Emits progress and then stalls; RaceRepository drives the finish so the
    race lands on an exact poll rather than on a sleep."""

    def __init__(self, repo): self.repo = repo

    def run(self, run_id):
        self.repo.add_event(run_id, "working", "Working")


class RaceRepository(Repository):
    """Completes the run at the exact poll where the stream has already drained
    every event, then writes the closing event a moment later -- the window the
    pipeline really leaves open between set_status and its final add_event.
    Driving this off the stream's own polling makes the race deterministic.
    """

    def __init__(self, url):
        super().__init__(url)
        self._finished = False
        self.fired = threading.Event()

    def events_since(self, run_id, sequence=0):
        rows = super().events_since(run_id, sequence)
        if not rows and not self._finished and super().get_run(run_id)["status"] not in TERMINAL:
            self._finished = True
            super().set_status(run_id, "completed")
            def close():
                super(RaceRepository, self).add_event(run_id, "completed", "Done", "complete")
                self.fired.set()
            threading.Timer(0.05, close).start()
        return rows


def test_stream_delivers_the_closing_event_written_after_the_terminal_status(tmp_path, settings):
    db = f"sqlite:///{tmp_path / 'sse.db'}"
    repo = RaceRepository(db); repo.init_schema()
    app = create_app(settings.model_copy(update={"database_url": db}), repo,
                     pipeline_factory=lambda: WorkingPipeline(repo))
    with TestClient(app) as client:
        run_id = client.post("/api/v1/runs", json={"items": [{"url": "https://example.com/news"}]}).json()["run_id"]
        with client.stream("GET", f"/api/v1/runs/{run_id}/events") as response:
            body = "".join(chunk for chunk in response.iter_text())
    assert repo.fired.is_set(), "the race this test exists for was never triggered"
    assert '"kind": "complete"' in body


class FinishingPipeline:
    def __init__(self, repo): self.repo = repo

    def run(self, run_id):
        self.repo.add_event(run_id, "working", "Working")
        self.repo.set_status(run_id, "completed")
        self.repo.add_event(run_id, "completed", "Done", "complete")


def test_reconnecting_stream_resumes_instead_of_replaying(tmp_path, settings):
    """An EventSource that drops and reconnects resends its last id; replaying
    the run from zero duplicated every line in the browser's progress list."""
    db = f"sqlite:///{tmp_path / 'resume.db'}"
    repo = Repository(db); repo.init_schema()
    app = create_app(settings.model_copy(update={"database_url": db}), repo,
                     pipeline_factory=lambda: FinishingPipeline(repo))
    with TestClient(app) as client:
        run_id = client.post("/api/v1/runs", json={"items": [{"url": "https://example.com/news"}]}).json()["run_id"]
        for _ in range(100):
            if repo.get_run(run_id)["status"] == "completed" and len(repo.events_since(run_id)) >= 3: break
            time.sleep(0.02)
        last = repo.events_since(run_id)[-1]["sequence"]
        with client.stream("GET", f"/api/v1/runs/{run_id}/events", headers={"Last-Event-ID": str(last)}) as response:
            body = "".join(chunk for chunk in response.iter_text())
    assert body.strip() == ""
