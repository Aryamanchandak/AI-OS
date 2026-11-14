"""The one adapter to glc_v5, which owns the models and the provider keys.

Used only to turn a request or a document into a proposed rule sheet. This app
holds no provider credential.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


class GatewayError(RuntimeError):
    """glc_v5 failed or could not be reached. Always shown to the user."""


class Gateway:
    def __init__(self, base_url: str, provider: str) -> None:
        self.base_url, self.provider = base_url.rstrip("/"), provider

    def json_reply(self, system: str, prompt: str) -> dict:
        """One chat call whose answer must be a single JSON object."""
        body = {"messages": [{"role": "user", "content": prompt}], "system": system,
                "max_tokens": 6000, "temperature": 0, "reasoning": "off",
                "provider": self.provider, "agent": "ftb_interpreter",
                "response_format": {"type": "json_object"}}
        request = urllib.request.Request(self.base_url + "/v1/chat", method="POST",
                                         data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                text = str(json.load(response).get("text", ""))
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:500]
            raise GatewayError(f"glc_v5 answered {error.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            reason = getattr(error, "reason", error)
            raise GatewayError(f"glc_v5 is not reachable at {self.base_url}: {reason}") from None
        return parse_json_object(text)


def parse_json_object(text: str) -> dict:
    candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        try:
            value = json.loads(candidate[start:end + 1]) if 0 <= start < end else None
        except json.JSONDecodeError:
            value = None
    if not isinstance(value, dict):
        raise GatewayError("the model did not return a JSON object; nothing was interpreted")
    return value
