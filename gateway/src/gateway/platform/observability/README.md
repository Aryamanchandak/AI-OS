# Tracing and operational diagnostics

This folder captures request/stage timing and selected operational metadata, exposes recent traces and budget refusals, and optionally exports traces to an OpenTelemetry collector.

| File | Responsibility |
| --- | --- |
| `__init__.py` | Implements `Telemetry`: creates the tracer and exporters, checks a configured collector's TCP reachability, reports sanitized export settings, and flushes/shuts down tracing. |
| `capture.py` | Implements the thread-safe `RecentTraceExporter`, bounded `RefusalLog`, and ASGI `DiagnosticCapture` middleware. |
| `redaction.py` | Implements `safe_error()` to flatten, truncate, and redact likely credentials in diagnostic strings. |
| `routes.py` | Exposes recent traces, individual trace details, and budget refusal history. |

## Data flow

Application startup initializes telemetry and attaches its tracer to the LLM pipeline. Middleware creates request spans for LLM API traffic; pipeline stages create child spans. The local exporter keeps up to 50 traces and 200 spans per trace by default. Refusal history retains up to 100 HTTP 402 events, with an allow-listed subset of their structured error details. These collections are process-local and disappear on restart.

Successful responses pass through without being buffered. Only 402 response bodies are captured, up to 16 KiB, for refusal processing. Exported local span attributes use an explicit allow-list rather than storing prompt/completion content.

Reads are `/api/observability/traces/recent`, `/traces/{trace_id}` and `/refusals` under the same prefix.

`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` or `OTEL_EXPORTER_OTLP_ENDPOINT` enables OTLP HTTP export; `OTEL_SERVICE_NAME` overrides the service name. An unreachable configured collector fails startup. Without a collector, local trace capture remains available.
