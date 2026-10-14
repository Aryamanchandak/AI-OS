from __future__ import annotations

import pytest

from glc import providers as P
from glc.routing import LIMITS


class _Response:
    status_code = 200
    text = ""

    def __init__(self, done_reason: str = "stop"):
        self.done_reason = done_reason

    def json(self):
        return {
            "message": {"content": "ok"},
            "prompt_eval_count": 2,
            "eval_count": 1,
            "done_reason": self.done_reason,
        }


class _Client:
    def __init__(self, response: _Response, seen: list[dict]):
        self.response = response
        self.seen = seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        self.seen.append(json)
        return self.response


@pytest.mark.asyncio
@pytest.mark.parametrize("done_reason", ["length", "max_tokens"])
async def test_ollama_config_disables_thinking_and_normalizes_truncation(monkeypatch, done_reason):
    seen: list[dict] = []
    monkeypatch.setattr(
        P.httpx,
        "AsyncClient",
        lambda **kwargs: _Client(_Response(done_reason), seen),
    )
    provider = P.OllamaProvider(
        "test-model",
        local_config={"needs_think_false": True},
    )
    result = await provider.chat([{"role": "user", "content": "hello"}], max_tokens=1)
    assert seen[0]["think"] is False
    assert result["stop_reason"] == "max_tokens"


def test_all_local_models_are_registered(monkeypatch):
    for key in list(P.os.environ):
        if key.endswith("API_KEY") or key.startswith("GEMINI_API_KEY_"):
            monkeypatch.delenv(key, raising=False)
    built = P.build_providers(cache_store=None)
    assert {"ollama", "gemma", "phi4-local", "cover-vision-local"} <= set(built)
    specs = P.load_local_models()
    for name, spec in specs.items():
        assert built[name].base_url == P.os.getenv("OLLAMA_URL", "http://localhost:11434")
        assert built[name].capabilities["vision"] is spec["vision"]
        assert LIMITS[name]["max_ctx"] == spec["context_window"]
