from fastapi.testclient import TestClient
import pytest

from main import AI_OS_ROOT, SCHEMA_AND_DOCS_PATHS, create_app


PROTECTED_PATHS = tuple(sorted(SCHEMA_AND_DOCS_PATHS))


def test_local_application_folders_are_connected() -> None:
    assert (AI_OS_ROOT / "gateway" / "main.py").is_file()


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_protected_paths_reject_a_missing_token(path: str) -> None:
    with TestClient(create_app(token="test-token")) as client:
        assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_protected_paths_reject_an_incorrect_token(path: str) -> None:
    with TestClient(create_app(token="test-token")) as client:
        response = client.get(path, headers={"Authorization": "Bearer wrong-token"})
        assert response.status_code == 401


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_protected_paths_accept_the_correct_token(path: str) -> None:
    with TestClient(create_app(token="test-token")) as client:
        response = client.get(path, headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 200


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_protected_paths_refuse_service_when_no_token_is_configured(path: str) -> None:
    with TestClient(create_app(token="")) as client:
        response = client.get(path, headers={"Authorization": "Bearer anything"})
        assert response.status_code == 503
        assert response.json()["detail"] == "AI_OS_TOKEN is not configured"


def test_health_needs_no_credentials() -> None:
    with TestClient(create_app(token="test-token")) as client:
        assert client.get("/health").status_code == 200


def test_health_stays_open_even_when_no_token_is_configured() -> None:
    with TestClient(create_app(token="")) as client:
        assert client.get("/health").json() == {"status": "ok"}


REMOVED_PATHS = (
    "/", "/dashboard", "/healthz", "/api/diagnostics/services",
    "/v1/providers", "/v1/refusals", "/v1/traces/recent",
    "/v1/observability/agent_trace/x", "/api/observability/agent_trace/x",
)


@pytest.mark.parametrize("path", REMOVED_PATHS)
def test_non_llm_features_are_gone(path: str) -> None:
    with TestClient(create_app(token="test-token")) as client:
        assert client.get(path, headers={"Authorization": "Bearer test-token"}).status_code == 404


@pytest.mark.parametrize("path", ("/v1/chat", "/v1/preflight"))
def test_v1_post_aliases_are_gone(path: str) -> None:
    with TestClient(create_app(token="test-token")) as client:
        response = client.post(path, headers={"Authorization": "Bearer test-token"}, json={"prompt": "hi"})
        assert response.status_code == 404
