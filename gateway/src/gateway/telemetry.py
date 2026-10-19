"""The only file that imports OpenTelemetry: tracer setup, request and stage spans, trace ids on replies.

With no OTLP endpoint configured, spans are created but go nowhere.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
import socket
from typing import Any
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import StatusCode
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gateway.platform.observability.redaction import safe_error


class Telemetry:
    def __init__(self) -> None:
        self.provider: TracerProvider | None = None
        self.tracer: Any = None
        self.endpoint = (
            os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
            or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
            or ""
        ).strip()

    def _check_export_target(self) -> None:
        if not self.endpoint:
            return
        parsed = urlparse(self.endpoint if "://" in self.endpoint else f"http://{self.endpoint}")
        if not parsed.hostname:
            raise ValueError(f"invalid OTLP endpoint: {self.endpoint!r}")
        port = parsed.port or (443 if parsed.scheme == "https" else 4318)
        try:
            with socket.create_connection((parsed.hostname, port), timeout=1):
                pass
        except OSError as exc:
            raise ConnectionError(
                f"OTel export target is unreachable: {parsed.hostname}:{port}: {exc}"
            ) from exc

    def initialize(self) -> None:
        self._check_export_target()
        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": os.getenv("OTEL_SERVICE_NAME", "ai-os-gateway")}
            )
        )
        if self.endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            endpoint = self.endpoint.rstrip("/")
            if not endpoint.endswith("/v1/traces"):
                endpoint += "/v1/traces"
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        if type(trace.get_tracer_provider()).__name__ == "ProxyTracerProvider":
            trace.set_tracer_provider(provider)
        self.provider = provider
        self.tracer = provider.get_tracer("gateway")

    def healthcheck(self) -> None:
        if self.provider is None or self.tracer is None:
            raise RuntimeError("telemetry was not initialized")
        self._check_export_target()

    def close(self) -> None:
        if self.provider is not None:
            self.provider.force_flush(5000)
            self.provider.shutdown()


@contextmanager
def stage_span(tracer: Any, name: str) -> Iterator[None]:
    """One child span per pipeline stage, marked as an error if the stage raises."""
    if tracer is None:
        yield
        return
    with tracer.start_as_current_span(name, record_exception=False, set_status_on_exception=False) as span:
        try:
            yield
        except BaseException:
            span.set_status(StatusCode.ERROR)
            raise


def chat_trace(result: dict[str, Any]) -> dict[str, Any]:
    """Tag the request span with provider, tokens and cost, and give the caller its trace id."""
    span = trace.get_current_span()
    context = span.get_span_context()
    output = dict(result)
    if context.is_valid:
        output["trace"] = {"trace_id": f"{context.trace_id:032x}", "span_id": f"{context.span_id:016x}", "url": None}
        for key, field in (("gen_ai.provider.name", "provider"), ("gen_ai.response.model", "model")):
            if result.get(field) is not None:
                span.set_attribute(key, safe_error(result[field]))
        for key, field in (("gen_ai.usage.input_tokens", "input_tokens"), ("gen_ai.usage.output_tokens", "output_tokens")):
            if isinstance(result.get(field), int):
                span.set_attribute(key, result[field])
        for key, section, field in (("glc.cost.usd", "cost", "total_usd"), ("glc.budget.admitted", "budget", "allowed")):
            value = (result.get(section) or {}).get(field)
            if isinstance(value, (int, float, bool)):
                span.set_attribute(key, value)
    return output


class RequestSpans:
    """ASGI middleware: one root span per `/api/llm/*` request. Never reads request or response bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        application = scope.get("app")
        container = getattr(application.state, "container", None) if application is not None else None
        if scope["type"] != "http" or container is None or not scope.get("path", "").startswith("/api/llm/"):
            await self.app(scope, receive, send)
            return
        status = 500
        with container.telemetry.tracer.start_as_current_span("http.request", record_exception=False, set_status_on_exception=False) as span:
            async def observed(message: Message) -> None:
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                await send(message)
            try:
                await self.app(scope, receive, observed)
            except BaseException:
                span.set_status(StatusCode.ERROR)
                raise
            finally:
                route = getattr(scope.get("route"), "path", "unknown")
                span.update_name(f"{scope.get('method', '')} {route}")
                span.set_attributes({"http.request.method": scope.get("method", ""), "http.route": route, "http.response.status_code": status})
                if status >= 400:
                    span.set_status(StatusCode.ERROR)
