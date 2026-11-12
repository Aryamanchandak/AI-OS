from fastapi.testclient import TestClient
import pytest
import time
from typing import Any

from main import AI_OS_ROOT, SCHEMA_AND_DOCS_PATHS, SHELL_DIST, create_app
import gateway.ingestion
import gateway.ingestion.preview


PROTECTED_PATHS = ("/api/ingestion/run", *sorted(SCHEMA_AND_DOCS_PATHS))
OPEN_PATHS = ("/health", "/ingestion", "/")


def test_local_application_folders_are_connected() -> None:
    assert (AI_OS_ROOT / "gateway" / "main.py").is_file()
    assert gateway.ingestion.__file__ is not None
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


def test_authorized_report_returns_the_typed_durable_record() -> None:
    headers = {"Authorization": "Bearer test-token"}
    with TestClient(create_app(token="test-token")) as client:
        report = client.get("/api/ingestion/run/preview-run/report", headers=headers)
        assert report.status_code == 200
        body = report.json()
        # The report body is returned directly, without the on-disk path.
        assert "path" not in body
        assert body["run_id"] == "preview-run"
        assert body["terminal_result"] == "complete"
        assert body["progress"]["intake_resolved"] == 2
        assert body["review"]["approve"] == 1
        assert [stage["status"] for stage in body["stages"]] == [
            "done",
            "done",
            "skipped",
        ]


def test_health_and_shell_are_available_but_ingestion_api_requires_bearer() -> None:
    with TestClient(create_app(token="test-token")) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ingestion").status_code == 200
        assert client.get("/api/ingestion/run").status_code == 401
        authorized = client.get(
            "/api/ingestion/run",
            headers={"Authorization": "Bearer test-token"},
        )
        assert authorized.status_code == 200
        assert authorized.json()["contract_version"] == "component6.v1"


def test_openapi_exposes_prefixed_ingestion_routes_only() -> None:
    app = create_app(token="test-token")
    paths = app.openapi()["paths"]
    assert "/api/ingestion/run" in paths
    assert "/api/ingestion/run/decision" in paths
    assert "/api/run" not in paths


def test_preview_lifecycle_reaches_confirmed_completion() -> None:
    headers = {"Authorization": "Bearer test-token"}
    with TestClient(create_app(token="test-token")) as client:
        client.post("/api/ingestion/run/start", headers=headers)

        def idle() -> dict[str, Any]:
            for _ in range(100):
                state: dict[str, Any] = client.get(
                    "/api/ingestion/run", headers=headers
                ).json()
                if state["operation"]["state"] != "submitting":
                    return state
                time.sleep(0.01)
            raise AssertionError("preview operation did not settle")

        book = idle()
        assert book["view"]["pending"]["adapter"] == "book_identity"
        client.post(
            "/api/ingestion/run/decision",
            headers=headers,
            json={
                "run_id": "preview-run",
                "item_id": "preview-book",
                "gate": "book_metadata",
                "action": "confirm",
                "payload": {},
                "expected_revision": book["operation"]["revision"],
            },
        )
        cleanup = idle()
        assert cleanup["view"]["pending"]["adapter"] == "cleanup"
        occurrence = cleanup["view"]["pending"]["payload"]["occurrence"]
        client.post(
            "/api/ingestion/run/decision",
            headers=headers,
            json={
                "run_id": "preview-run",
                "item_id": "preview-cleanup",
                "gate": "cleanup",
                "action": "apply_once",
                "payload": {
                    "occurrence_id": occurrence["occurrence_id"],
                    "expected_interaction_revision": 0,
                    "expected_working_draft_revision": 0,
                },
                "expected_revision": cleanup["operation"]["revision"],
            },
        )
        image = idle()
        assert image["view"]["pending"]["adapter"] == "image_ocr"
        client.post(
            "/api/ingestion/run/decision",
            headers=headers,
            json={
                "run_id": "preview-run",
                "item_id": "preview-image",
                "gate": "content_approval",
                "action": "approve",
                "payload": {
                    "passages": [{"index": 0, "edited_text": "Corrected."}],
                    "page_number": 42,
                },
                "expected_revision": image["operation"]["revision"],
            },
        )
        complete = idle()
        assert complete["view"]["terminal_result"] == "complete"
        assert complete["view"]["pending"] is None
