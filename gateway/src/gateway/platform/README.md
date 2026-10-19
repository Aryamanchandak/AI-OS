# Shared platform infrastructure

This folder contains infrastructure shared by gateway domains. It supplies the mechanisms for configuration, persistence, HTTP connections, and telemetry; domain repositories still own their own schemas and business behavior.

| File or folder | Responsibility |
| --- | --- |
| `startup.py` | Runs named `StartupCheck` callbacks and converts failures to `StartupDependencyError`, which includes a machine-readable event describing the failed dependency and cause. |
| [configuration](configuration/README.md) | Loads process settings and resolves configuration/database paths. |
| [database](database/README.md) | Provides SQLite connection, transaction, and migration helpers. |
| [networking](networking/README.md) | Owns the reusable outbound HTTP client. |
| [observability](observability/README.md) | Owns tracing, bounded diagnostic storage, redaction, and diagnostic routes. |
| `__init__.py` | Declares the package. |

[Application lifespan](../app/README.md) constructs and checks this infrastructure before serving requests. `run_startup_checks()` stops at the first failing check instead of silently allowing startup to continue.
