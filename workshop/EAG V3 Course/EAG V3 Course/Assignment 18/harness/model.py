"""The only file that talks to a model. Every call returns the same small dict."""
import json
import time
import urllib.request


class OllamaModel:
    """A local model served by Ollama. No key, no cost, no outside network."""

    def __init__(self, name, options, think=False, host="http://localhost:11434", timeout_s=300):
        self.name, self.options, self.think = name, options, think
        self.host, self.timeout_s = host, timeout_s

    def chat(self, messages):
        body = {
            "model": self.name,
            "messages": messages,
            "stream": False,
            "format": "json",
            "think": self.think,
            "options": self.options,
        }
        request = urllib.request.Request(
            self.host + "/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read())
            return {
                "ok": True,
                "text": data["message"]["content"],
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "seconds": round(time.monotonic() - started, 2),
                "error": None,
            }
        except Exception as error:  # an infrastructure failure, not an agent outcome
            detail = error.read().decode(errors="replace")[:500] if hasattr(error, "read") else ""
            message = f"{type(error).__name__}: {error} {detail}".strip()
            failed = _failed(message, time.monotonic() - started)
            if "prediction aborted" in detail:
                # The server was up and the model was generating; it got stuck
                # repeating itself. That is a reply the agent could not use,
                # not an outage, so the run carries on.
                failed["ok"] = True
            return failed


class ScriptedModel:
    """Replays fixed replies. Used by the tests and to run attacks without a model."""

    def __init__(self, replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]

    def chat(self, messages):
        if not self.replies:
            return _failed("script exhausted", 0)
        return {
            "ok": True,
            "text": self.replies.pop(0),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "seconds": 0.0,
            "error": None,
        }


def _failed(error, seconds):
    return {
        "ok": False,
        "text": "",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "seconds": round(seconds, 2),
        "error": error,
    }
