"""Bounded, thread-safe trace and refusal storage; never stores HTTP content."""
from __future__ import annotations

from collections import OrderedDict, deque
import copy
import json
from threading import RLock
import time
from typing import Any

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gateway.platform.observability.redaction import safe_error


class RecentTraceExporter(SpanExporter):
    def __init__(self, limit: int = 50, max_spans: int = 200) -> None:
        self.limit, self.max_spans = limit, max_spans
        self.traces: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self.lock = RLock()

    def export(self, spans: Any) -> SpanExportResult:
        with self.lock:
            for span in spans:
                trace_id = f"{span.context.trace_id:032x}"
                rows = self.traces.setdefault(trace_id, [])
                attrs = {key: value for key, value in (span.attributes or {}).items()
                         if key in {"http.request.method", "http.route", "http.response.status_code",
                                    "gen_ai.provider.name", "gen_ai.response.model",
                                    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
                                    "glc.cost.usd", "glc.cache.hit", "glc.budget.admitted"}}
                rows.append({
                    "name": span.name, "trace_id": trace_id,
                    "span_id": f"{span.context.span_id:016x}",
                    "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None,
                    "start_time": span.start_time, "end_time": span.end_time,
                    "duration_ns": (span.end_time or 0) - (span.start_time or 0),
                    "status": span.status.status_code.name, "attributes": attrs,
                })
                del rows[:-self.max_spans]
                self.traces.move_to_end(trace_id)
                while len(self.traces) > self.limit:
                    self.traces.popitem(last=False)
        return SpanExportResult.SUCCESS

    def summaries(self, limit: int = 25) -> list[dict[str, Any]]:
        with self.lock:
            result = []
            for trace_id, spans in reversed(self.traces.items()):
                root = min(spans, key=lambda row: row["start_time"])
                start = min(row["start_time"] for row in spans)
                end = max(row["end_time"] for row in spans)
                result.append({
                    "trace_id": trace_id, "root_span": root["name"], "spans": len(spans),
                    "started_at": start / 1e9, "duration_ms": (end - start) / 1e6,
                    "status": "ERROR" if any(row["status"] == "ERROR" for row in spans) else "OK",
                    **dict.fromkeys(("provider_instance", "role", "tier", "url")),
                    "cost_usd": root["attributes"].get("glc.cost.usd"),
                    "cache_hit": root["attributes"].get("glc.cache.hit"),
                    "budget_admitted": root["attributes"].get("glc.budget.admitted"),
                    "provider": root["attributes"].get("gen_ai.provider.name"),
                    "model": root["attributes"].get("gen_ai.response.model"),
                    "input_tokens": root["attributes"].get("gen_ai.usage.input_tokens"),
                    "output_tokens": root["attributes"].get("gen_ai.usage.output_tokens"),
                })
                if len(result) >= max(1, min(limit, 200)):
                    break
            return result

    def detail(self, trace_id: str) -> dict[str, Any] | None:
        with self.lock:
            rows = self.traces.get(trace_id)
            return {"trace_id": trace_id, "url": None, "spans": copy.deepcopy(rows)} if rows else None

    def shutdown(self) -> None:
        pass


class RefusalLog:
    def __init__(self, limit: int = 100) -> None:
        self.events: deque[dict[str, Any]] = deque(maxlen=limit)
        self.total = 0
        self.lock = RLock()

    def record(self, method: str, path: str, body: bytes) -> None:
        try:
            payload = json.loads(body).get("detail")
        except (ValueError, AttributeError):
            payload = None
        allowed = {"error", "code", "message", "principal", "dimension", "period", "period_start", "limit_usd", "spent_usd", "remaining_usd", "projected_usd", "shortfall_usd", "checked", "hint", "value", "reserved_usd", "fraction_used", "source"}

        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items() if key in allowed}
            if isinstance(value, list):
                return [clean(item) for item in value[:100]]
            return safe_error(value) if isinstance(value, str) else value

        with self.lock:
            self.total += 1
            self.events.appendleft({"ts": time.time(), "status": 402, "method": method, "path": path,
                                    "detail": clean(payload) if isinstance(payload, dict) else None})

    def describe(self, limit: int = 25) -> dict[str, Any]:
        with self.lock:
            return {"watching": [402], "total": self.total, "kept": len(self.events),
                    "refusals": copy.deepcopy(list(self.events)[:max(1, min(limit, 100))])}


class DiagnosticCapture:
    """Observe streaming requests without buffering successful responses."""
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        application = scope.get("app")
        container = getattr(application.state, "container", None) if application is not None else None
        path = scope.get("path", "")
        if scope["type"] != "http" or container is None or not path.startswith(("/api/llm/", "/v1/")) or path.startswith(("/v1/traces", "/v1/observability", "/v1/refusals", "/api/observability")):
            await self.app(scope, receive, send)
            return
        telemetry = container.telemetry
        body = bytearray()
        status = 500
        with telemetry.tracer.start_as_current_span("http.request", record_exception=False, set_status_on_exception=False) as span:
            async def observed(message: Message) -> None:
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                if message["type"] == "http.response.body" and status == 402:
                    body.extend(message.get("body", b"")[:max(0, 16384 - len(body))])
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
                if status == 402:
                    telemetry.refusals.record(scope.get("method", ""), route, bytes(body))
