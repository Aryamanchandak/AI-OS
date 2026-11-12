"""Python client for LLM Gateway V7. Adds an embed() method on top of V3."""
import os, json, httpx
from typing import Any, Optional

DEFAULT_URL = os.getenv("LLM_GATEWAY_V7_URL", "http://localhost:8107")


class LLM:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = 600):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, prompt: str = None, *,
             messages: Optional[list] = None,
             system: Any = None,
             profile: str = None,
             provider: str = None, model: str = None,
             max_tokens: int = 2048, temperature: float = 0.7,
             tools: Optional[list] = None,
             tool_choice: Any = None,
             cache_system: Optional[bool] = None,
             reasoning: Optional[str] = None,
             response_format: Any = None) -> dict:
        body = {
            "prompt": prompt, "messages": messages, "system": system,
            "profile": profile,
            "provider": provider, "model": model,
            "max_tokens": max_tokens, "temperature": temperature, "stream": False,
            "tools": tools, "tool_choice": tool_choice,
            "cache_system": cache_system, "reasoning": reasoning,
            "response_format": response_format,
        }
        body = {k: v for k, v in body.items() if v is not None}
        r = httpx.post(f"{self.base_url}/v1/chat", json=body, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def stream(self, prompt: str = None, *, messages=None, system=None,
               profile: str = None,
               provider: str = None, model: str = None,
               max_tokens: int = 2048, temperature: float = 0.7,
               tools=None, tool_choice=None,
               cache_system=None, reasoning=None, response_format=None,
               result_sink: Optional[dict] = None):
        """Yield text deltas from a streaming chat call.

        Pass ``result_sink={}`` to receive the ``done`` event payload after the
        generator exhausts — the dict is populated in-place with ``provider``,
        and (when ``response_format`` with a schema was used) ``parsed`` and
        the validated ``text``.  On a gateway error the dict gets ``error``.
        """
        body = {
            "prompt": prompt, "messages": messages, "system": system,
            "profile": profile,
            "provider": provider, "model": model,
            "max_tokens": max_tokens, "temperature": temperature, "stream": True,
            "tools": tools, "tool_choice": tool_choice,
            "cache_system": cache_system, "reasoning": reasoning,
            "response_format": response_format,
        }
        body = {k: v for k, v in body.items() if v is not None}
        with httpx.stream("POST", f"{self.base_url}/v1/chat", json=body, timeout=self.timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                d = json.loads(line[6:])
                if "delta" in d:
                    yield d["delta"]
                if d.get("done") or d.get("error"):
                    if result_sink is not None:
                        result_sink.update(d)
                    return

    def capabilities(self):
        return httpx.get(f"{self.base_url}/v1/capabilities", timeout=30).json()

    def resolve_chat_profile(self, profile: str) -> dict:
        """Return the exact provider/model pin or fail if it is unavailable."""
        r = httpx.get(
            f"{self.base_url}/v1/chat/profiles/{profile}",
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def embed(self, text: str,
              task_type: str = "retrieval_document",
              provider: Optional[str] = None,
              profile: Optional[str] = None) -> dict:
        """Returns {provider, model, embedding, dim, latency_ms, attempted, profile}.

        Pass `profile` (e.g. "chunker-v1") instead of `provider` to pin the
        call to an exact provider+model pair defined server-side in
        embedders.PROFILES. The gateway verifies the response actually matches
        the pin and raises (HTTP 500) rather than silently returning a
        different model's vectors. `profile` and `provider` are mutually
        exclusive.
        """
        body = {"text": text, "task_type": task_type}
        if provider:
            body["provider"] = provider
        if profile:
            body["profile"] = profile
        r = httpx.post(f"{self.base_url}/v1/embed", json=body, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def status(self) -> dict:
        return httpx.get(f"{self.base_url}/v1/status", timeout=30).json()

    def embedders(self) -> dict:
        return httpx.get(f"{self.base_url}/v1/embedders", timeout=30).json()

    def preflight(self, *, embedding_profile: str = "chunker-v1",
                  chat_provider: Optional[str] = None) -> dict:
        """Verify the gateway can actually serve a structured chat completion
        and the required embedding profile, before a live run starts.

        Makes one real minimal call against each path (not just a status/rate
        check) so a down Ollama daemon or a misconfigured provider is caught
        here instead of mid-run. Returns a checks dict on success; raises
        GatewayPreflightError (with `.checks` populated) if either path
        failed.
        """
        checks: dict[str, dict] = {}

        try:
            r = self.chat(
                'Return exactly this JSON object and nothing else: {"ok": true}',
                provider=chat_provider,
                max_tokens=256,
                reasoning="off",
                response_format={
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"ok": {"type": "boolean"}},
                        "required": ["ok"],
                    },
                    "name": "preflight",
                },
            )
            checks["chat"] = {"ok": True, "provider": r.get("provider"), "model": r.get("model")}
        except Exception as exc:
            checks["chat"] = {"ok": False, "error": str(exc)}

        try:
            r = self.embed("preflight check", profile=embedding_profile)
            checks["embedding"] = {
                "ok": True,
                "provider": r.get("provider"),
                "model": r.get("model"),
                "dim": r.get("dim"),
            }
        except Exception as exc:
            checks["embedding"] = {"ok": False, "error": str(exc)}

        if not (checks["chat"]["ok"] and checks["embedding"]["ok"]):
            raise GatewayPreflightError("gateway preflight failed", checks)
        return checks


class GatewayPreflightError(Exception):
    """Raised by LLM.preflight() when chat or the required embedding profile
    is not actually usable. `.checks` holds the per-path result dict so the
    caller can log/report exactly which side failed."""

    def __init__(self, msg: str, checks: dict):
        super().__init__(f"{msg}: {checks}")
        self.checks = checks


def ask(prompt: str, provider: str = None, **kw) -> str:
    return LLM().chat(prompt, provider=provider, **kw)["text"]


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else None
    print(ask("Say hello in one short line.", provider=p))
