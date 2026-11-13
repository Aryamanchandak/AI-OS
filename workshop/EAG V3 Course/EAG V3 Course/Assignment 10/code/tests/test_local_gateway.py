"""Check the bundled gateway connection without starting any services."""

import importlib.util
import shutil
import sys
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    code = tmp_path / "code"
    gateway = tmp_path / "llm_gatewayV9"
    code.mkdir()
    gateway.mkdir()
    shutil.copyfile(ROOT / "code/gateway.py", code / "gateway.py")
    shutil.copyfile(ROOT / "llm_gatewayV9/client.py", gateway / "client.py")
    # Register restoration even when the variable was originally absent;
    # load_dotenv later writes directly to the environment.
    monkeypatch.setenv("LLM_GATEWAY_V9_URL", "")
    monkeypatch.delenv("LLM_GATEWAY_V9_URL")

    def no_network(*args, **kwargs):
        pytest.fail("Importing the gateway must not make a network request")

    monkeypatch.setattr(httpx, "get", no_network)
    monkeypatch.setattr(httpx, "post", no_network)
    yield tmp_path


def load_bridge(bundle):
    spec = importlib.util.spec_from_file_location(
        "assignment_gateway_test", bundle / "code/gateway.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_uses_gateway_inside_assignment(bundle):
    schemas_before = sys.modules.get("schemas")
    module = load_bridge(bundle)
    assert module.GATEWAY_V9_DIR == bundle / "llm_gatewayV9"
    assert module.LLM is not None
    assert module.LLM().base_url == module.GATEWAY_URL == "http://localhost:8109"
    assert sys.modules.get("schemas") is schemas_before


def test_loads_root_dotenv_before_loading_gateway_client(bundle):
    (bundle / ".env").write_text("LLM_GATEWAY_V9_URL=http://localhost:18109\n")
    module = load_bridge(bundle)
    assert module.GATEWAY_URL == "http://localhost:18109"
    assert module.LLM().base_url == module.GATEWAY_URL


def test_existing_environment_takes_precedence(bundle, monkeypatch):
    (bundle / ".env").write_text("LLM_GATEWAY_V9_URL=http://localhost:18109\n")
    monkeypatch.setenv("LLM_GATEWAY_V9_URL", "http://localhost:28109")
    module = load_bridge(bundle)
    assert module.GATEWAY_URL == "http://localhost:28109"
    assert module.LLM().base_url == module.GATEWAY_URL
