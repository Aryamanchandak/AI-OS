from __future__ import annotations

import asyncio
import json
import socket
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .models import CompletionRequest, CompletionResponse, TokenUsage


class ProviderError(RuntimeError):
    """A provider-boundary failure safe to display to an end user."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.endpoint = _completion_endpoint(base_url)
        self.api_key = api_key
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = float(timeout)

    async def __call__(self, request: CompletionRequest) -> CompletionResponse:
        payload = request_to_openai(request)
        return await asyncio.to_thread(self._send, payload)

    def _send(self, payload: Mapping[str, Any]) -> CompletionResponse:
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            raise ProviderError("Completion request contains a non-JSON value") from None
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise ProviderError(
                f"Provider request failed with HTTP {error.code}", status_code=error.code
            ) from None
        except (TimeoutError, socket.timeout):
            raise ProviderError("Provider request timed out") from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise ProviderError("Provider request timed out") from None
            raise ProviderError("Provider request could not be completed") from None
        except OSError:
            raise ProviderError("Provider request could not be completed") from None

        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderError("Provider returned malformed JSON") from None
        return response_from_openai(decoded)


def _completion_endpoint(base_url: str) -> str:
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("base_url must be a non-empty HTTP(S) URL")
    parts = urlsplit(base_url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("base_url must be a valid HTTP(S) URL")
    if parts.query or parts.fragment or parts.username or parts.password:
        raise ValueError("base_url cannot contain credentials, a query, or a fragment")
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        endpoint_path = path
    else:
        endpoint_path = f"{path}/chat/completions"
    return urlunsplit((parts.scheme, parts.netloc, endpoint_path, "", ""))


def request_to_openai(request: CompletionRequest) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    if request.system:
        messages.append({"role": "system", "content": request.system})
    for message in request.messages:
        messages.extend(_message_to_openai(message))

    payload: dict[str, Any] = {"model": request.model, "messages": messages, "stream": False}
    if request.tools:
        payload["tools"] = [_tool_to_openai(tool) for tool in request.tools]
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    return payload


def _message_to_openai(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(message, Mapping):
        raise ProviderError("Completion message must be an object")
    role = message.get("role")
    if role not in {"system", "user", "assistant"}:
        raise ProviderError("Completion message has an unsupported role")
    content = message.get("content", "")
    if isinstance(content, str):
        return [{"role": role, "content": content}]
    if not _is_sequence(content):
        raise ProviderError("Completion message content must be text or a block list")

    result: list[dict[str, Any]] = []
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal text_parts, tool_calls
        if not text_parts and not tool_calls:
            return
        item: dict[str, Any] = {"role": role, "content": "\n".join(text_parts) or None}
        if tool_calls:
            if role != "assistant":
                raise ProviderError("tool_use blocks require an assistant message")
            item["tool_calls"] = tool_calls
        result.append(item)
        text_parts = []
        tool_calls = []

    for block in content:
        if not isinstance(block, Mapping):
            raise ProviderError("Completion content blocks must be objects")
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if not isinstance(text, str):
                raise ProviderError("Text blocks require string text")
            text_parts.append(text)
        elif block_type == "tool_use":
            identifier = block.get("id")
            name = block.get("name")
            arguments = block.get("input")
            if not isinstance(identifier, str) or not identifier or not isinstance(name, str) or not name:
                raise ProviderError("tool_use blocks require string id and name")
            if not isinstance(arguments, Mapping):
                raise ProviderError("tool_use input must be an object")
            tool_calls.append(
                {
                    "id": identifier,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": _encode_arguments(arguments),
                    },
                }
            )
        elif block_type == "tool_result":
            flush()
            identifier = block.get("tool_use_id")
            if not isinstance(identifier, str) or not identifier:
                raise ProviderError("tool_result blocks require a string tool_use_id")
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": identifier,
                    "content": _tool_result_text(block.get("content", "")),
                }
            )
        else:
            raise ProviderError("Completion contains an unsupported content block")
    flush()
    return result or [{"role": role, "content": ""}]


def _tool_result_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if _is_sequence(value):
        parts: list[str] = []
        for block in value:
            if not isinstance(block, Mapping) or block.get("type") != "text" or not isinstance(
                block.get("text"), str
            ):
                raise ProviderError("tool_result content must contain only text blocks")
            parts.append(block["text"])
        return "\n".join(parts)
    raise ProviderError("tool_result content must be text or text blocks")


def _encode_arguments(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise ProviderError("tool_use input must contain only JSON values") from None


def _tool_to_openai(tool: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(tool, Mapping):
        raise ProviderError("Tool definitions must be objects")
    name = tool.get("name")
    schema = tool.get("input_schema")
    if not isinstance(name, str) or not name or not isinstance(schema, Mapping):
        raise ProviderError("Tool definitions require a name and input_schema object")
    function: dict[str, Any] = {"name": name, "parameters": dict(schema)}
    description = tool.get("description")
    if description is not None:
        if not isinstance(description, str):
            raise ProviderError("Tool descriptions must be strings")
        function["description"] = description
    return {"type": "function", "function": function}


def response_from_openai(payload: Any) -> CompletionResponse:
    if not isinstance(payload, Mapping):
        raise ProviderError("Provider response must be a JSON object")
    choices = payload.get("choices")
    if not _is_sequence(choices) or not choices or not isinstance(choices[0], Mapping):
        raise ProviderError("Provider response is missing a completion choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise ProviderError("Provider completion choice is missing a message")

    blocks: list[Mapping[str, Any]] = []
    content = message.get("content")
    if content is not None:
        if not isinstance(content, str):
            raise ProviderError("Provider message content must be text or null")
        if content:
            blocks.append({"type": "text", "text": content})
    tool_calls = message.get("tool_calls", [])
    if not _is_sequence(tool_calls):
        raise ProviderError("Provider tool_calls must be a list")
    for call in tool_calls:
        if not isinstance(call, Mapping) or call.get("type", "function") != "function":
            raise ProviderError("Provider returned a malformed tool call")
        identifier = call.get("id")
        function = call.get("function")
        if not isinstance(identifier, str) or not identifier or not isinstance(function, Mapping):
            raise ProviderError("Provider returned a malformed tool call")
        name = function.get("name")
        encoded_arguments = function.get("arguments")
        if not isinstance(name, str) or not name or not isinstance(encoded_arguments, str):
            raise ProviderError("Provider returned a malformed tool call")
        try:
            arguments = json.loads(encoded_arguments)
        except json.JSONDecodeError:
            raise ProviderError("Provider tool call arguments contain malformed JSON") from None
        if not isinstance(arguments, Mapping):
            raise ProviderError("Provider tool call arguments must decode to an object")
        blocks.append({"type": "tool_use", "id": identifier, "name": name, "input": arguments})

    finish_reason = choice.get("finish_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        raise ProviderError("Provider finish_reason must be text or null")
    stop_reason = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
    }.get(finish_reason, finish_reason)
    usage = _usage_from_openai(payload.get("usage", {}))
    metadata = {
        key: payload[key]
        for key in ("id", "model", "created", "system_fingerprint")
        if key in payload
    }
    metadata["finish_reason"] = finish_reason
    return CompletionResponse(tuple(blocks), stop_reason, usage, metadata)


def _usage_from_openai(value: Any) -> TokenUsage:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ProviderError("Provider usage must be an object")
    prompt = _usage_integer(value, "prompt_tokens")
    completion = _usage_integer(value, "completion_tokens")
    cached = 0
    details = value.get("prompt_tokens_details")
    if details is not None:
        if not isinstance(details, Mapping):
            raise ProviderError("Provider prompt token details must be an object")
        cached = _usage_integer(details, "cached_tokens")
    return TokenUsage(prompt, completion, cached, 0)


def _usage_integer(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key, 0)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise ProviderError("Provider usage contains an invalid token count")
    return item


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


__all__ = [
    "OpenAICompatibleProvider",
    "ProviderError",
    "request_to_openai",
    "response_from_openai",
]
