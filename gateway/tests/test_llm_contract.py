"""Route contract for the migrated LLM router.

Checks that every legacy GLC path still answers at its new `/api/llm` path.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from gateway.app import get_llm_service
from gateway.app import create_app
from gateway.app import API_PREFIX, router
from test_llm import FakeProvider, service_for

#: The old→new mapping from Plan 04a §7. Left side is a legacy GLC path; right
#: side is where it must now answer.
ROUTE_MAPPING = {
    "/v1/chat": "/api/llm/chat",
    "/v1/embed": "/api/llm/embed",
    "/v1/embedders": "/api/llm/embedders",
    "/v1/providers": "/api/llm/providers",
    "/v1/capabilities": "/api/llm/capabilities",
    "/v1/status": "/api/llm/status",
    "/v1/budget": "/api/llm/budget",
    "/v1/cost/by_principal": "/api/llm/cost/by_principal",
    "/v1/pricing": "/api/llm/pricing",
}


def migrated_paths() -> dict[str, set[str]]:
    """Every path the LLM router registers, with the methods it answers."""
    out: dict[str, set[str]] = {}
    for route in router.routes:
        path = f"{API_PREFIX}{route.path}"
        out.setdefault(path, set()).update(m for m in route.methods if m not in {"HEAD", "OPTIONS"})
    return out


def test_every_mapped_route_exists_at_its_new_path() -> None:
    paths = migrated_paths()
    missing = [f"{old} -> {new}" for old, new in ROUTE_MAPPING.items() if new not in paths]
    assert missing == [], f"mapped routes absent from the migrated router: {missing}"


@pytest.fixture
def client(tmp_path: Path):
    service, _ = service_for(tmp_path, [FakeProvider("solo")])
    app = create_app(token="test-token")
    app.dependency_overrides[get_llm_service] = lambda: service
    # These route contracts use an isolated service without application startup.
    return TestClient(app, headers={"Authorization": "Bearer test-token"})


@pytest.mark.parametrize("prefix", ["/api/llm"])
@pytest.mark.parametrize("route", ["routers", "telemetry"])
def test_placeholder_routes_are_removed(client: TestClient, prefix: str, route: str) -> None:
    assert client.get(f"{prefix}/{route}").status_code == 404


@pytest.mark.parametrize("prefix", ["/api/llm"])
@pytest.mark.parametrize(
    ("route", "removed", "retained"),
    [
        ("embedders", {"fixed_dim", "max_input_chars", "backoff_steps_s", "live"},
         {"order", "models", "profiles", "today"}),
        ("status", {"live", "limits"}, {"order", "today"}),
        ("providers", {"shortcuts", "limits"},
         {"order", "providers", "models", "chat_profiles"}),
    ],
)
def test_diagnostics_omit_placeholder_fields(
    client: TestClient, prefix: str, route: str, removed: set[str], retained: set[str],
) -> None:
    response = client.get(f"{prefix}/{route}")
    assert response.status_code == 200
    body = response.json()
    assert removed.isdisjoint(body)
    assert retained <= body.keys()


@pytest.mark.parametrize('prefix', ['/api/llm'])
def test_streaming_is_rejected_with_a_clear_error(client: TestClient, prefix: str) -> None:
    response = client.post(f'{prefix}/chat', json={'prompt': 'hello', 'stream': True})
    assert response.status_code == 422
    assert 'streaming is not supported' in response.text.lower()


@pytest.mark.parametrize('prefix', ['/api/llm'])
@pytest.mark.parametrize(('method', 'route'), [('GET', 'stats'), ('POST', 'purge')])
def test_response_cache_routes_are_removed(client: TestClient, prefix: str, method: str, route: str) -> None:
    assert client.request(method, f'{prefix}/cache/{route}').status_code == 404


def test_explicit_stream_false_returns_completed_json(client: TestClient) -> None:
    response = client.post('/api/llm/chat', json={'prompt': 'hello', 'stream': False})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/json')
    assert response.json()['text'] == 'ok'
    assert 'cache' not in response.json()


@pytest.mark.parametrize(('field', 'value'), [
    ('batch', True), ('auto_route', 'decision'), ('cost_quality_tradeoff', .5),
    ('escalate', True), ('tenant', 'one'), ('project', 'one'), ('user', 'one'),
])
def test_removed_request_options_are_rejected(client: TestClient, field: str, value) -> None:
    response = client.post('/api/llm/chat', json={'prompt': 'hello', field: value})
    assert response.status_code == 422
    assert any(error['loc'] == ['body', field] and error['type'] == 'extra_forbidden'
               for error in response.json()['detail'])


@pytest.mark.parametrize('prefix', ['/api/llm'])
@pytest.mark.parametrize(('route', 'body'), [('chat/batch', {'calls': []}), ('vision', {'prompt': 'read', 'image': 'data:image/png;base64,AAAA'})])
def test_unused_chat_routes_are_removed(client, prefix, route, body) -> None:
    assert client.post(f'{prefix}/{route}', json=body).status_code == 404


@pytest.mark.parametrize('dimension', ['tenant', 'project', 'user'])
def test_removed_budget_dimensions_are_rejected(client, dimension) -> None:
    assert client.post('/api/llm/budget', json={'principal': f'{dimension}:*', 'limit_usd': 1}).status_code == 400
    assert client.get('/api/llm/cost/by_principal', params={'dimension': dimension}).status_code == 400


@pytest.mark.parametrize('dimension', ['agent', 'session'])
def test_agent_and_session_runtime_budgets_work(client, dimension) -> None:
    from gateway.pricing import PricingTable

    service = client.app.dependency_overrides[get_llm_service]()
    service.pricing = PricingTable({'unpriced_default': {'input': 1, 'output': 1}})
    response = client.post('/api/llm/budget', json={'principal': f'{dimension}:*', 'limit_usd': 0})
    assert response.status_code == 200
    assert response.json()['policy']['dimension'] == dimension
    refused = client.post('/api/llm/chat', json={'prompt': 'hello', dimension: 'run-1'})
    assert refused.status_code == 402
    assert refused.json()['detail']['dimension'] == dimension


def test_cost_rollups_expose_only_agent_and_session(client) -> None:
    assert client.post('/api/llm/chat', json={'prompt': 'hello', 'agent': 'reader', 'session': 'run-1'}).status_code == 200
    result = client.get('/api/llm/cost/by_principal').json()
    assert result['dimensions'] == ['agent', 'session']
    assert set(result['by_dimension']) == {'agent', 'session'}
    assert result['by_dimension']['agent'][0]['value'] == 'reader'
    assert result['by_dimension']['session'][0]['value'] == 'run-1'


@pytest.mark.parametrize('block', [
    {'type': 'image_url', 'image_url': {'url': 'https://example.test/image.png'}},
    {'type': 'image_url', 'image_url': 'http://example.test/image.png'},
    {'type': 'input_image', 'url': 'https://example.test/image.png'},
    {'type': 'image', 'source': {'type': 'url', 'url': 'https://example.test/image.png'}},
])
def test_image_links_are_rejected_without_network_access(client, monkeypatch, block) -> None:
    import socket
    import httpx

    def no_dns(*args, **kwargs):
        raise AssertionError('Image links must not trigger DNS resolution')

    async def no_download(*args, **kwargs):
        raise AssertionError('Image links must not trigger downloads')

    monkeypatch.setattr(socket, 'getaddrinfo', no_dns)
    monkeypatch.setattr(httpx.AsyncClient, 'send', no_download)
    response = client.post('/api/llm/chat', json={'messages': [{'role': 'user', 'content': [block]}]})
    assert response.status_code == 400
    assert 'send the image as a data: URL' in response.json()['detail']


def test_image_transcription_profile_uses_the_local_model() -> None:
    from gateway.profiles import ProfileRegistry

    profiles = ProfileRegistry.from_yaml(Path(__file__).resolve().parents[1] / 'config/profiles.yaml')
    spec = profiles.resolve('chat', 'image-transcription-v1')
    assert spec['provider'] == 'gemma'
    assert spec['model'] == 'gemma4:12b'


def _client_for(service) -> TestClient:
    app = create_app(token="test-token")
    app.dependency_overrides[get_llm_service] = lambda: service
    return TestClient(app, headers={"Authorization": "Bearer test-token"})


def test_calls_survive_a_restart(tmp_path: Path) -> None:
    import asyncio
    from gateway.models import ChatRequest

    first, _ = service_for(tmp_path, [FakeProvider("solo")])
    asyncio.run(first.chat(ChatRequest(prompt="hello", agent="reader")))
    restarted, _ = service_for(tmp_path, [FakeProvider("solo")])
    calls = _client_for(restarted).get("/api/llm/calls").json()
    assert [(row["agent"], row["provider"]) for row in calls] == [("reader", "solo")]


def test_cost_by_agent_equals_the_sum_of_ledger_rows(tmp_path: Path) -> None:
    import asyncio
    from gateway.models import ChatRequest

    service, ledger = service_for(tmp_path, [FakeProvider("solo")], price=1)
    for agent, session in [("reader", "run-1"), ("reader", "run-2"), ("writer", "run-1")]:
        asyncio.run(service.chat(ChatRequest(prompt="hello", agent=agent, session=session)))
    client = _client_for(service)
    by_agent = {row["value"]: row for row in client.get("/api/llm/cost/by_agent").json()}
    for agent in ("reader", "writer"):
        mine = [row for row in ledger.recent() if row["agent"] == agent]
        assert by_agent[agent]["calls"] == len(mine)
        assert by_agent[agent]["dollars"] == pytest.approx(sum(row["usd"] for row in mine))
    one_session = client.get("/api/llm/cost/by_agent", params={"session": "run-1"}).json()
    assert {row["value"]: row["calls"] for row in one_session} == {"reader": 1, "writer": 1}
