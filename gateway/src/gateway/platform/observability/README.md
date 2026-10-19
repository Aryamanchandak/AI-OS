# Redaction

`redaction.py` implements `safe_error()`, which flattens, truncates and redacts likely credentials in strings that go into error replies and trace attributes.

Tracing itself lives in [`gateway/telemetry.py`](../../telemetry.py), the only file that imports OpenTelemetry. `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` or `OTEL_EXPORTER_OTLP_ENDPOINT` turns on export; `OTEL_SERVICE_NAME` overrides the service name. An unreachable configured collector fails startup. With no collector, spans go nowhere: there is no in-process trace store.
