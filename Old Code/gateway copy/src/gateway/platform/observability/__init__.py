"""Fail-fast OpenTelemetry lifecycle ownership."""

from __future__ import annotations

import os
import socket
from typing import Any
from urllib.parse import urlparse
from gateway.platform.observability.capture import RecentTraceExporter, RefusalLog


class Telemetry:
    def __init__(self) -> None:
        self.provider: Any = None
        self.tracer: Any = None
        self.recent = RecentTraceExporter()
        self.refusals = RefusalLog()
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
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": os.getenv("OTEL_SERVICE_NAME", "ai-os-gateway")}
            )
        )
        provider.add_span_processor(SimpleSpanProcessor(self.recent))
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

    def describe(self) -> dict[str, object]:
        parsed = urlparse(self.endpoint)
        # Diagnostics never expose collector userinfo, query credentials, or fragments.
        public_endpoint = None
        if parsed.hostname:
            host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
            public_endpoint = f"{parsed.scheme}://{host}" + (f":{parsed.port}" if parsed.port else "") + parsed.path
        return {"active": self.tracer is not None,
                "service_name": os.getenv("OTEL_SERVICE_NAME", "ai-os-gateway"),
                "endpoint": public_endpoint,
                "traces_endpoint": (public_endpoint.rstrip("/") if public_endpoint.endswith("/v1/traces") else public_endpoint.rstrip("/") + "/v1/traces") if public_endpoint else None,
                "protocol": "http/protobuf" if self.endpoint else None,
                "exporters": ["in_memory", *(["otlp/http"] if self.endpoint else [])],
                "capture_content": False, "trace_ui": None}

    def healthcheck(self) -> None:
        if self.provider is None or self.tracer is None:
            raise RuntimeError("telemetry was not initialized")
        self._check_export_target()

    def close(self) -> None:
        if self.provider is not None:
            self.provider.force_flush(5000)
            self.provider.shutdown()
