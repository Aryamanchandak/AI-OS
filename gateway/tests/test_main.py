from fastapi.testclient import TestClient
import pytest

from main import AI_OS_ROOT, SCHEMA_AND_DOCS_PATHS, SHELL_DIST, create_app


PROTECTED_PATHS = ("/api/diagnostics/services", *sorted(SCHEMA_AND_DOCS_PATHS))
OPEN_PATHS = ("/health", "/")


def test_local_application_folders_are_connected() -> None:
    assert (AI_OS_ROOT / "gateway" / "main.py").is_file()
    assert SHELL_DIST == AI_OS_ROOT / "shell" / "dist"


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


@pytest.mark.parametrize("path", OPEN_PATHS)
def test_health_and_shell_entry_need_no_credentials(path: str) -> None:
    with TestClient(create_app(token="test-token")) as client:
        assert client.get(path).status_code == 200


def test_health_stays_open_even_when_no_token_is_configured() -> None:
    with TestClient(create_app(token="")) as client:
        assert client.get("/health").json() == {"status": "ok"}
