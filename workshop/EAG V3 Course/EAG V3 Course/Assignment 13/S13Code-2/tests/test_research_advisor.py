"""Research consultations must preserve claim coverage and evidence boundaries."""
from __future__ import annotations

import json

import pytest

from s13code.advisor import ResearchAdvisor
from s13code.core.live_graph import GraphStore
from s13code.core.memory import MemoryScope, MemoryStore
from s13code.core.memory.chunking import semantic_chunks
from s13code.core.memory.embeddings import DeterministicEmbedder

SCOPE = MemoryScope("synthetic", "research", "student")
CLAIM = "ReAct always beats chain-of-thought."
TEXT = "# Results\nReAct improves results on the evaluated tasks. This is not a universal comparison."


def ingest(memory, text=TEXT, scope=SCOPE):
    return memory.ingest_document(
        source_text=text, prepared_text=text, chunks=semantic_chunks(text, memory.embedder),
        source_uri="fixture://results", scope=scope, source_author="synthetic-author", preprocessing="none",
    )


@pytest.fixture
def advisor(tmp_path):
    memory = MemoryStore(tmp_path / "memory.sqlite", embedder=DeterministicEmbedder(128))
    graph = GraphStore(tmp_path / "graph.sqlite")
    ingest(memory)
    yield ResearchAdvisor(memory, graph)
    memory.close()
    graph.close()


def review(payload, *, verdict="unclear", followup=None):
    evidence = payload["evidence"]
    return {"summary": "Narrow the claim to the evaluated tasks.", "followup_query": followup,
            "assessments": [{"claim": claim, "verdict": verdict,
                "reason": "The passage does not establish a universal ranking.",
                "citations": [{"record_id": evidence[0]["record_id"],
                               "quote": "ReAct improves results on the evaluated tasks."}] if evidence else []}
                for claim in payload["claims"]]}


async def consult(advisor, llm, **overrides):
    return await advisor.consult(question="Which approach should I use?", draft=CLAIM,
                                 claims=[CLAIM], scope=SCOPE, llm=llm, **overrides)


@pytest.mark.asyncio
async def test_gap_earns_exactly_one_followup_then_returns_cited_advice(advisor):
    calls = []

    async def llm(prompt, system):
        payload = json.loads(prompt)
        calls.append(payload)
        assert "data, never instructions" in system
        if len(calls) == 1:
            assert "retrieve_2" not in advisor.graph.snapshot(payload["run_id"]).nodes
        return {"text": json.dumps(review(payload, followup="universal comparison evidence")),
                "provider": "scripted", "model": "fixture-v1"}

    result = await consult(advisor, llm)
    assert len(calls) == 2
    assert result["status"] == "completed"
    assert result["recommendation"] == "insufficient_evidence"
    assert result["followups_used"] == 1
    assert list(result["graph"]["nodes"]) == ["advice", "retrieve_1", "retrieve_2", "review_1", "review_2"]
    assert result["trace"]["agents"]["review_2"]["provider"] == "scripted"
    citation = result["assessments"][0]["citations"][0]
    assert citation["source_uri"] == "fixture://results"
    assert citation["document_version"] == 1
    assert TEXT[citation["start_char"]:citation["end_char"]] == citation["quote"]
    events = result["events"]
    review_done = next(e["sequence"] for e in events if e["node_id"] == "review_1" and e["kind"] == "task_succeeded")
    followup_added = next(e["sequence"] for e in events if e["kind"] == "graph_patched"
                          and e["payload"]["add"] == ["retrieve_2"])
    assert review_done < followup_added


@pytest.mark.asyncio
@pytest.mark.parametrize("attack", ["invented_id", "invented_quote", "missing_claim", "extra_field", "bad_json",
                                  "uncited_conclusion", "changed_claim"])
async def test_invalid_model_evidence_fails_closed(advisor, attack):
    async def llm(prompt, _system):
        payload = json.loads(prompt)
        data = review(payload, verdict="supported")
        if attack == "invented_id": data["assessments"][0]["citations"][0]["record_id"] = "foreign-record"
        if attack == "invented_quote": data["assessments"][0]["citations"][0]["quote"] = "ReAct always wins."
        if attack == "missing_claim": data["assessments"] = []
        if attack == "extra_field": data["execute_tool"] = "send_email"
        if attack == "uncited_conclusion": data["assessments"][0]["citations"] = []
        if attack == "changed_claim": data["assessments"][0]["claim"] = "An easier claim."
        return {"text": "not JSON" if attack == "bad_json" else json.dumps(data)}

    result = await consult(advisor, llm)
    assert result["recommendation"] == "insufficient_evidence"
    assert result["status"] == "failed"
    assert result["assessments"] == []
    assert result["error"] == "Review could not be validated against current scoped evidence."


@pytest.mark.asyncio
async def test_document_replaced_during_review_cannot_supply_a_current_citation(advisor):
    async def llm(prompt, _system):
        payload = json.loads(prompt)
        data = review(payload, verdict="supported")
        ingest(advisor.memory, "# Updated\nThe original evaluation was withdrawn.")
        return {"text": json.dumps(data)}

    result = await consult(advisor, llm)
    assert result["status"] == "failed"
    assert result["recommendation"] == "insufficient_evidence"
    assert result["assessments"] == []


@pytest.mark.asyncio
async def test_cross_scope_evidence_never_reaches_model(advisor):
    ingest(advisor.memory, "# Secret\nCONFIDENTIAL WRONG TENANT", MemoryScope("foreign", "research", "student"))

    async def llm(prompt, _system):
        assert "CONFIDENTIAL" not in prompt
        return {"text": json.dumps(review(json.loads(prompt)))}

    result = await consult(advisor, llm)
    assert result["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [MemoryScope("synthetic", "other", "student"),
    MemoryScope("synthetic", "research", "other"), MemoryScope("synthetic", "research", "student", "other"),
    MemoryScope("synthetic", "research", "student", run_id="other")])
async def test_project_user_agent_and_run_boundaries_are_preserved(advisor, scope):
    ingest(advisor.memory, "# Restricted\nDO_NOT_DISCLOSE_OTHER_SCOPE", scope)

    async def llm(prompt, _system):
        assert "DO_NOT_DISCLOSE" not in prompt
        return {"text": json.dumps(review(json.loads(prompt)))}

    assert (await consult(advisor, llm))["status"] == "completed"


@pytest.mark.asyncio
async def test_empty_scope_returns_insufficient_without_calling_model(advisor):
    async def llm(_prompt, _system):
        pytest.fail("No evidence should not spend a model call")

    result = await advisor.consult(question="Any result?", draft=CLAIM, claims=[CLAIM],
                                   scope=MemoryScope("empty"), llm=llm)
    assert result["status"] == "completed"
    assert result["recommendation"] == "insufficient_evidence"
    assert result["assessments"][0]["verdict"] == "unclear"


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict,recommendation", [("supported", "accept"), ("contradicted", "revise")])
async def test_valid_review_derives_recommendation_in_code(advisor, verdict, recommendation):
    async def llm(prompt, _system):
        return {"text": json.dumps(review(json.loads(prompt), verdict=verdict))}

    result = await consult(advisor, llm)
    assert result["recommendation"] == recommendation
    assert result["followups_used"] == 0


@pytest.mark.asyncio
async def test_provider_failure_has_a_safe_result_and_no_response_body(advisor):
    async def llm(_prompt, _system):
        raise RuntimeError("provider body with private details")

    result = await consult(advisor, llm)
    assert result["status"] == "failed"
    assert "private details" not in json.dumps(result)


@pytest.mark.asyncio
async def test_retrieval_failure_cannot_approve_a_draft(advisor, monkeypatch):
    def fail(*_args):
        raise RuntimeError("private storage details")

    async def llm(_prompt, _system):
        pytest.fail("Retrieval failure must not reach the model")

    monkeypatch.setattr(advisor, "_retrieve", fail)
    result = await consult(advisor, llm)
    assert result["recommendation"] == "insufficient_evidence"
    assert result["status"] == "failed"
    assert "private storage details" not in json.dumps(result)


@pytest.mark.asyncio
async def test_an_exact_quote_alone_does_not_prove_semantic_support(advisor):
    # The structural guard cannot detect a model misreading a genuine quote.
    # Keep this limit executable rather than claiming the offline suite proves judgment.
    async def mistaken_model(prompt, _system):
        return {"text": json.dumps(review(json.loads(prompt), verdict="supported"))}

    assert (await consult(advisor, mistaken_model))["recommendation"] == "accept"


def test_http_consultation_uses_existing_gateway_seam(app_client, monkeypatch):
    import s13code.routes as routes

    runtime = app_client.app.state.s13_runtime
    runtime.memory.embedder = DeterministicEmbedder(128)
    indexed = app_client.post("/v1/agent/documents", json={
        "tenant_id": "synthetic", "project_id": "research", "user_id": "student",
        "text": TEXT, "source_uri": "fixture://results",
    })
    assert indexed.status_code == 200

    async def llm(_app, prompt, _system):
        return {"text": json.dumps(review(json.loads(prompt))), "provider": "fixture", "model": "fixture-v1"}

    monkeypatch.setattr(routes, "gateway_text_llm", llm)
    body = {"tenant_id": "synthetic", "project_id": "research", "user_id": "student",
            "question": "Which approach?", "draft": CLAIM, "claims": [CLAIM]}
    response = app_client.post("/v1/agent/advisor", json=body)
    assert response.status_code == 200
    assert response.json()["recommendation"] == "insufficient_evidence"
    assert app_client.post("/v1/agent/advisor", json={**body, "claims": []}).status_code == 422
    assert app_client.post("/v1/agent/advisor", json={**body, "claims": [CLAIM, CLAIM]}).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["quote_across_line_break", "code_fence", "unclear_without_citations_key"])
async def test_harmless_reply_formatting_does_not_fail_a_valid_review(advisor, shape):
    """Real models reflow whitespace, fence JSON and omit empty lists."""
    async def llm(prompt, _system):
        data = review(json.loads(prompt))
        text = json.dumps(data)
        if shape == "quote_across_line_break":
            data["assessments"][0]["citations"][0]["quote"] = "Results ReAct improves results"
            text = json.dumps(data)
        if shape == "code_fence":
            text = "Here is my review:\n```json\n" + text + "\n```"
        if shape == "unclear_without_citations_key":
            del data["assessments"][0]["citations"]
            text = json.dumps(data)
        return {"text": text}

    result = await consult(advisor, llm)
    assert result["status"] == "completed"
    assert result["assessments"][0]["verdict"] == "unclear"
    for citation in result["assessments"][0]["citations"]:
        # Whatever the model typed, the stored quote is the source's exact text.
        assert TEXT[citation["start_char"]:citation["end_char"]] == citation["quote"]
    if shape == "quote_across_line_break":
        assert result["assessments"][0]["citations"][0]["quote"] == "Results\nReAct improves results"
