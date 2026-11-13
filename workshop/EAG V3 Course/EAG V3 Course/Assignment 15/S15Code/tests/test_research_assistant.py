"""Real course passages are the acceptance example; model replies are test doubles."""
import json
from pathlib import Path

import pytest

from s15code.core.live_graph import GraphStore
from s15code.research.models import Document, GradeRequest, LearningRequest, ResearchRequest
from s15code.research.service import ResearchAssistant
from s15code.research.sources import retrieve

ROOT = Path(__file__).resolve().parents[2]
QUESTION = "When does cheaper-model routing save money per resolved task?"


def documents():
    return [Document(name="Assignment.md", text=(ROOT / "Assignment.md").read_text()),
            Document(name="README.md", text=(ROOT / "S15Code/README.md").read_text())]


def reply(evidence):
    passage = next(e for e in evidence if "cost per resolved task" in e["text"].lower())
    claim = {"text": "Compare cost per resolved task, including quality and retries.",
             "citations": [{"evidence_id": passage["id"], "quote": "cost per resolved task"}]}
    return {"title": "Cheaper calls need sufficient resolution", "conclusions": [claim],
            "alternatives": [claim], "uncertainties": ["The course does not measure this user's workload."]}


class Transport:
    def __init__(self, invalid=False):
        self.calls = []
        self.invalid = invalid

    async def chat(self, *, prompt, system, request=None):
        self.calls.append((prompt, system, request))
        payload = json.loads(prompt)
        result = reply(payload["evidence"])
        if payload["task"] == "cards":
            result = {"cards": [{"question": "Which cost metric should you compare?",
                                 "answer": result["conclusions"][0]}]}
        elif payload["task"] == "grade":
            result = {"verdict": "correct", "explanation": result["conclusions"][0]}
        if self.invalid:
            result["conclusions"][0]["citations"][0]["quote"] = "a fabricated source quote"
        return {"text": json.dumps(result), "provider": request["provider"], "model": request["model"],
                "input_tokens": 100, "output_tokens": 150}


@pytest.fixture
def assistant(tmp_path):
    store = GraphStore(tmp_path / "graph.sqlite")
    yield ResearchAssistant(store)
    store.close()


def test_retrieval_quotes_round_trip_to_real_documents():
    docs = documents()
    evidence = retrieve(QUESTION, docs)
    assert evidence and any("resolved task" in e["text"].lower() for e in evidence)
    for passage in evidence:
        original = docs[passage["document_index"]].text.splitlines()
        assert passage["text"] == "\n".join(original[passage["line_start"] - 1:passage["line_end"]])


@pytest.mark.asyncio
async def test_course_brief_is_cited_metered_and_journalled(assistant):
    transport = Transport()
    result = await assistant.research(ResearchRequest(question=QUESTION, documents=documents()), transport)
    assert result["status"] == "completed"
    assert "resolved task" in result["output"]["conclusions"][0]["text"]
    assert len(result["budget"]["charges"]) == len(transport.calls) == 1
    assert result["budget"]["spent"] > 0
    assert result["trace"]["trace_id"]
    assert [e["sequence"] for e in result["events"]] == sorted(e["sequence"] for e in result["events"])
    assert assistant.read(result["run_id"])["output"] == result["output"]


@pytest.mark.asyncio
async def test_invented_quote_is_rejected_but_paid_call_survives(assistant):
    result = await assistant.research(ResearchRequest(question=QUESTION, documents=documents()), Transport(True))
    assert result["status"] == "failed"
    assert result["output"] is None
    assert "quote" in result["error"].lower()
    assert result["budget"]["spent"] > 0
    assert any(e["kind"] == "task_failed" for e in result["events"])
    assert any(e["payload"].get("metered_calls") for e in result["events"])


@pytest.mark.asyncio
async def test_unaffordable_request_is_visible_without_spending(assistant):
    transport = Transport()
    result = await assistant.research(ResearchRequest(question=QUESTION, documents=documents(), budget=1e-10),
                                      transport)
    assert result["status"] == "refused"
    assert transport.calls == []
    assert result["budget"]["spent"] == 0
    assert result["budget"]["refusals"]
    assert any(e["kind"] == "task_failed" for e in result["events"])


def test_ui_and_example_available_without_a_model(app_client):
    response = app_client.get("/research")
    assert response.status_code == 200
    assert "Research desk" in response.text
    assert app_client.get("/research/app.js").status_code == 200
    assert app_client.get("/research/style.css").status_code == 200
    example = app_client.get("/v1/research/example").json()
    assert example["question"] == QUESTION
    assert len(example["documents"]) >= 2
    assert app_client.post("/v1/research/runs", json={"question": "?", "documents": []}).status_code == 422


@pytest.mark.asyncio
async def test_learning_reuses_the_verified_sources_and_server_card(assistant):
    transport = Transport()
    research = await assistant.research(ResearchRequest(question=QUESTION, documents=documents()), transport)
    cards = await assistant.cards(LearningRequest(research_run_id=research["run_id"]), transport)
    assert cards["status"] == "completed"
    assert cards["evidence"] == research["evidence"]
    grade = await assistant.grade(GradeRequest(cards_run_id=cards["run_id"], card_index=0,
                                              answer="Cost per resolved task."), transport)
    assert grade["output"]["verdict"] == "correct"
    assert json.loads(transport.calls[-1][0])["card"] == cards["output"]["cards"][0]
    assert len(transport.calls) == 3
    assert sum(r["budget"]["spent"] for r in [research, cards, grade]) > 0
    assert assistant.read(research["run_id"])["trace"]["trace_id"] == research["trace"]["trace_id"]


@pytest.mark.asyncio
async def test_learning_cannot_run_on_a_failed_brief(assistant):
    research = await assistant.research(ResearchRequest(question=QUESTION, documents=documents()), Transport(True))
    transport = Transport()
    with pytest.raises(ValueError, match="completed"):
        await assistant.cards(LearningRequest(research_run_id=research["run_id"]), transport)
    assert transport.calls == []


def test_http_research_learning_and_grading_share_the_runtime(app_client):
    app_client.app.state.gateway.chat = Transport().chat
    research = app_client.post("/v1/research/runs", json={"question": QUESTION,
        "documents": [d.model_dump() for d in documents()]}).json()
    assert research["status"] == "completed"
    cards = app_client.post("/v1/research/cards", json={"research_run_id": research["run_id"]}).json()
    assert cards["status"] == "completed"
    grade = app_client.post("/v1/research/grade", json={"cards_run_id": cards["run_id"],
        "card_index": 0, "answer": "Compare cost per resolved task, including retries."}).json()
    assert grade["status"] == "completed"
    assert grade["output"]["verdict"] == "correct"
    assert app_client.get("/v1/research/runs/unknown").status_code == 404
    assert app_client.post("/v1/research/grade", json={"cards_run_id": cards["run_id"],
        "card_index": 5, "answer": "x"}).status_code == 422
