import time
from fastapi.testclient import TestClient

from consequence_radar.web.app import create_app
from consequence_radar.storage import Repository


class CompletingPipeline:
    def __init__(self,repo): self.repo=repo
    def run(self,run_id):
        self.repo.save_artifact(run_id,"graph",{"version":1,"nodes":[],"edges":[]})
        self.repo.set_status(run_id,"completed");self.repo.add_event(run_id,"completed","Done","complete")

def test_api_submit_status_events_graph_and_restart(tmp_path,settings):
    db=f"sqlite:///{tmp_path/'api.db'}";repo=Repository(db);repo.init_schema()
    app=create_app(settings.model_copy(update={"database_url":db}),repo,pipeline_factory=lambda:CompletingPipeline(repo))
    with TestClient(app) as client:
        response=client.post('/api/v1/runs',json={"items":[{"url":"https://example.com/news"}]})
        assert response.status_code==202;run_id=response.json()['run_id']
        for _ in range(30):
            if client.get(f'/api/v1/runs/{run_id}').json()['status']=='completed':break
            time.sleep(.01)
        assert client.get(f'/api/v1/runs/{run_id}/graph').status_code==200
        page=client.get(f'/runs/{run_id}');assert page.status_code==200 and 'Causal graph' in page.text
        assert client.get('/health').json()['database']=='ok'
    restarted=Repository(db);restarted.init_schema();assert restarted.get_run(run_id)['status']=='completed'


def test_browser_form_has_working_server_fallback_and_validation(tmp_path, settings):
    db = f"sqlite:///{tmp_path/'form.db'}"
    repo = Repository(db)
    repo.init_schema()
    app = create_app(
        settings.model_copy(update={"database_url": db}),
        repo,
        pipeline_factory=lambda: CompletingPipeline(repo),
    )

    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'action="/runs" method="post"' in page.text
        assert 'name="news"' in page.text

        invalid = client.post("/runs", data={"news": "not an article URL"})
        assert invalid.status_code == 422
        assert "complete http:// or https:// article URLs" in invalid.text
        assert "not an article URL" in invalid.text

        submitted = client.post(
            "/runs",
            data={"news": "https://example.com/one\nhttps://example.com/two"},
            follow_redirects=False,
        )
        assert submitted.status_code == 303
        assert submitted.headers["location"].startswith("/runs/")

        # A persisted batch is a dictionary. Bracket access is required in
        # Jinja because dot access resolves ``items`` to dict.items.
        history = client.get("/")
        assert history.status_code == 200
        assert "2 supplied items" in history.text
