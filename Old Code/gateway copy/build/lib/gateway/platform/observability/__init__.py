"""Fail-fast OpenTelemetry lifecycle ownership."""

from __future__ import annotations

import os
import socket
from typing import Any
from urllib.parse import urlparse


class Telemetry:
    def __init__(self) -> None:
        self.provider: Any = None
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
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

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
