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
    "/api/observability/traces/recent", "/api/observability/traces/x", "/api/observability/refusals",
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


SECRET = "sk-ant-test-secret-value-1234"
AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """No provider keys in the process, a private ledger, and a temporary `.env` path."""
    import gateway.config

    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, "")  # recorded, so the teardown removes whatever .env loads
        monkeypatch.delenv(name)
    monkeypatch.setenv("GLC_GATEWAY_DB", str(tmp_path / "gateway.sqlite"))
    env_file = tmp_path / ".env"
    monkeypatch.setattr(gateway.config, "ENV_FILE", env_file)
    return env_file


def test_a_key_in_dotenv_makes_its_provider_appear(isolated_env) -> None:
    isolated_env.write_text("ANTHROPIC_API_KEY=test\n", encoding="utf-8")
    with TestClient(create_app(token="test-token")) as client:
        assert "anthropic" in client.get("/api/llm/providers", headers=AUTH).json()["providers"]


def test_the_gateway_starts_without_a_dotenv_file(isolated_env) -> None:
    assert not isolated_env.exists()
    with TestClient(create_app(token="test-token")) as client:
        providers = client.get("/api/llm/providers", headers=AUTH).json()["providers"]
        assert "anthropic" not in providers and "openai" not in providers


def test_the_key_value_never_appears_in_responses_or_logs(isolated_env, caplog) -> None:
    isolated_env.write_text(f"ANTHROPIC_API_KEY={SECRET}\n", encoding="utf-8")
    caplog.set_level("DEBUG")
    with TestClient(create_app(token="test-token")) as client:
        for path in ("/api/llm/providers", "/api/llm/capabilities", "/api/llm/status", "/api/llm/embedders"):
            assert SECRET not in client.get(path, headers=AUTH).text
    assert SECRET not in caplog.text


def test_the_key_value_never_appears_in_startup_errors(isolated_env, caplog) -> None:
    from gateway.app import StartupCheck

    def broken() -> None:
        raise RuntimeError("dependency down")

    isolated_env.write_text(f"ANTHROPIC_API_KEY={SECRET}\n", encoding="utf-8")
    with pytest.raises(Exception) as error:
        with TestClient(create_app(token="test-token", startup_checks=(StartupCheck("broken", broken),))):
            pass
    assert SECRET not in str(error.value) and SECRET not in caplog.text


def test_the_bearer_token_can_come_from_dotenv(isolated_env, monkeypatch) -> None:
    monkeypatch.delenv("AI_OS_TOKEN")
    isolated_env.write_text("AI_OS_TOKEN=from-dotenv\n", encoding="utf-8")
    with TestClient(create_app()) as client:
        assert client.get("/api/llm/providers", headers={"Authorization": "Bearer from-dotenv"}).status_code == 200
