# Service address registry

This folder provides validated, non-secret addresses for AI OS services. It is a configuration lookup, rather than a live service-discovery or health-monitoring system.

`registry.py` defines `ServiceDefinition` (host, port, enabled, required), `ServiceRegistry`, the YAML loader, and `gateway_address()`. `__init__.py` re-exports those public objects.

## Loading and use

1. Load `config/services.yaml`, or a caller-supplied path.
2. Validate service names and endpoint fields.
3. Apply `AI_OS_SERVICE_<NAME>_HOST`, `_PORT`, and `_ENABLED` overrides.
4. Reject duplicate ports among enabled services.
5. Expose service lookup, IPv6-aware HTTP URL construction, and allow-listed diagnostics.

`url_for()` rejects disabled services. `gateway_address()` also requires the gateway entry to be both enabled and required, and supports `AI_OS_SERVICE_REGISTRY_PATH`. The `required` flag is metadata here; loading the registry does not contact services.

The application uses this registry for `/api/diagnostics/services`, the legacy `/healthz` port response, and the configured agent-runtime trace target. See [observability](../observability/README.md).
