from consequence_radar.models import NewsBatch, NewsItem, NewsletterReport
from consequence_radar.storage import Repository


def test_complete_handbuilt_run_roundtrips_without_loss(tmp_path, graph):
    repo = Repository(f"sqlite:///{tmp_path / 'roundtrip.db'}"); repo.init_schema()
    batch = NewsBatch(items=[NewsItem(url="https://example.com/news")])
    run_id = repo.create_run(batch)
    repo.save_artifact(run_id, "graph", graph, version=1)
    graph2 = graph.model_copy(update={"version": 2})
    repo.save_artifact(run_id, "graph", graph2, version=2)
    repo.save_artifact(run_id, "claims", [{"id":"C1","source_id":"S1","passage_verified":True}])
    repo.save_artifact(run_id, "report", NewsletterReport(headline="Headline", dek="Dek text", why_this_matters="This is a substantive market explanation.", article_markdown="Analysis text", central_case_summary="This is the most supported coherent central case.", key_assumptions=["The policy is implemented on schedule"], what_changes_the_view=["Implementation delay"], source_ids_used=["S1"]))
    assert repo.artifact(run_id, "graph")["version"] == 2
    assert repo.artifact(run_id, "graph", version=1)["estimates"][0]["central"] is None
    assert repo.get_run(run_id)["batch"]["items"][0]["url"] == "https://example.com/news"
    assert len(repo.events_since(run_id)) == 1

def test_path_with_question_mark_roundtrips(tmp_path):
    path = tmp_path / "dir?name" / "db.sqlite"
    repo = Repository(f"sqlite:///{path}"); repo.init_schema()
    assert repo.create_run(NewsBatch(items=[NewsItem(url="https://example.com")]))
