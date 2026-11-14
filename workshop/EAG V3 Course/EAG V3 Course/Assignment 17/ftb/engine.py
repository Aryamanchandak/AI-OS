"""The one adapter to S17Code. Nothing else in this app talks to the engine.

Three calls, each verified against the engine's own source:

  POST /v1/agent/runs        starts a run and answers only when it has finished
  GET  /v1/agent/runs/{id}   the durable journal: nodes, edges, ordered events
  GET  /healthz              is anything there

The journal is read rather than the AG-UI stream at /v1/runs/{id}/events
because the AG-UI mapping drops what the activity panel needs most: which
capability a node is, and which nodes a planner patch added.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

# What a build is allowed to do in the workspace: write the page, edit it, and
# run the allow-listed check. Nothing that sends, deletes or resets.
BUILD_SIDE_EFFECTS = ["create_file", "edit_code", "run_command"]


class EngineError(RuntimeError):
    """The engine refused, failed, or could not be reached. Always shown to the user."""


class Engine:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url, self.token = base_url.rstrip("/"), token

    def _call(self, method: str, path: str, body: dict | None = None, *, timeout: float) -> Any:
        request = urllib.request.Request(
            self.base_url + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:500]
            if error.code == 404:
                raise KeyError(path) from None
            raise EngineError(f"S17Code answered {error.code} on {path}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            reason = getattr(error, "reason", error)
            raise EngineError(f"S17Code is not reachable at {self.base_url}: {reason}") from None

    def health(self) -> dict:
        return self._call("GET", "/healthz", timeout=3)

    def start_run(self, run_id: str, prompt: str, *, timeout: float) -> dict:
        """Blocks until the run ends. The caller chose `run_id`, so it can be watched meanwhile."""
        return self._call("POST", "/v1/agent/runs", timeout=timeout, body={
            "tenant_id": "ftb", "project_id": "financial-tools", "user_id": "builder",
            "agent_id": "ftb", "prompt": prompt, "run_id": run_id,
            "allowed_side_effects": BUILD_SIDE_EFFECTS,
        })

    def journal(self, run_id: str) -> dict | None:
        """The run so far, or None if the engine has not created it yet."""
        try:
            return self._call("GET", f"/v1/agent/runs/{run_id}", timeout=10)
        except KeyError:
            return None
