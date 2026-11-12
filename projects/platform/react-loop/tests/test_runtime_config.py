from pathlib import Path

from simple_server.config import app_url
from simple_server.tools.generative_ui import render_ui, render_ui_from_json
from simple_server.tools.files import file_create, file_write_json


def test_app_url_defaults_to_localhost_8000(monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)

    assert app_url("/ui/latest") == "http://127.0.0.1:8000/ui/latest"


def test_app_url_supports_non_default_port(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:8001")

    assert app_url("/ui/latest") == "http://127.0.0.1:8001/ui/latest"


def test_app_url_supports_custom_https_host_and_trailing_slash(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://example.com/")

    assert app_url("/ui/latest") == "https://example.com/ui/latest"


def test_app_url_supports_base_path(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://example.com/react-loop/")

    assert app_url("/ui/latest") == "https://example.com/react-loop/ui/latest"


def test_render_ui_uses_configured_base_url(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    monkeypatch.setenv("APP_BASE_URL", "https://example.com/react-loop/")
    code = """
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Heading, Text

with PrefabApp() as app:
    with Column():
        Heading("Configured URL", level=2)
        Text("ok")
"""

    ui_out = render_ui(code)

    assert "https://example.com/react-loop/ui/latest" in ui_out
    assert "127.0.0.1:8000" not in ui_out


def test_render_ui_from_json_uses_persisted_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    file_write_json("rows.json", [{"name": "Persisted Alpha", "value": 3}])
    code = """
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Heading, Text

with PrefabApp() as app:
    with Column():
        Heading("Rows", level=2)
        Text(data[0]["name"])
"""

    out = render_ui_from_json("rows.json", code)
    snapshot = Path(tmp_path) / "generated_ui" / "index.html"

    assert "UI rendered successfully from rows.json" in out
    assert "Persisted Alpha" in snapshot.read_text(encoding="utf-8")


def test_render_ui_from_json_changes_when_file_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    code = """
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Text

with PrefabApp() as app:
    with Column():
        Text(data[0]["name"])
"""
    file_write_json("rows.json", [{"name": "First"}])
    render_ui_from_json("rows.json", code)
    first = (Path(tmp_path) / "generated_ui" / "index.html").read_text(encoding="utf-8")

    file_write_json("rows.json", [{"name": "Second"}], overwrite=True)
    render_ui_from_json("rows.json", code)
    second = (Path(tmp_path) / "generated_ui" / "index.html").read_text(encoding="utf-8")

    assert "First" in first
    assert "Second" in second
    assert first != second


def test_render_ui_from_json_rejects_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))

    out = render_ui_from_json("missing.json", "from prefab_ui.app import PrefabApp")

    assert out.startswith("ERROR:")
    assert "does not exist" in out


def test_render_ui_from_json_rejects_invalid_source_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    (Path(tmp_path) / "bad.json").write_text("{'bad': True}", encoding="utf-8")

    out = render_ui_from_json("bad.json", "from prefab_ui.app import PrefabApp")

    assert out.startswith("ERROR: Invalid JSON")
    assert not (Path(tmp_path) / "generated_ui" / "index.html").exists()


def test_render_ui_from_json_rejects_code_that_ignores_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    file_write_json("rows.json", [{"name": "Persisted Alpha"}])
    code = """
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Text

with PrefabApp() as app:
    with Column():
        Text("Substitute data")
"""

    out = render_ui_from_json("rows.json", code)

    assert out.startswith("ERROR:")
    assert "did not read the persisted JSON" in out
    assert not (Path(tmp_path) / "generated_ui" / "index.html").exists()
